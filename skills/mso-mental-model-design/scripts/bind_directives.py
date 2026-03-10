#!/usr/bin/env python3
"""Bind directives from vertex registry to topology nodes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # frontmatter parsing fallback

PACK_ROOT = Path(__file__).resolve().parents[3]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    """Parse YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    if yaml is not None:
        return yaml.safe_load(parts[1])
    # minimal fallback: key: value lines
    fm: Dict[str, Any] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip("'\"") for x in v[1:-1].split(",")]
            fm[k.strip()] = v
    return fm


def _load_registry(registry_path: Path) -> List[Dict[str, Any]]:
    """Load all directive frontmatters from registry directory."""
    directives: List[Dict[str, Any]] = []
    for md in sorted(registry_path.rglob("*.md")):
        fm = _parse_frontmatter(md)
        if fm and fm.get("id") and fm.get("type"):
            fm["_path"] = str(md.relative_to(registry_path))
            directives.append(fm)
    return directives


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _match_score(directive: Dict[str, Any], vertex_type: str, motif: str, domain: str) -> float:
    score = 0.0
    vtypes = directive.get("applicable_vertex_types") or []
    if isinstance(vtypes, list) and vertex_type in vtypes:
        score += 0.4
    motifs = directive.get("applicable_motifs") or []
    if isinstance(motifs, list) and motif in motifs:
        score += 0.3
    if directive.get("domain") == domain:
        score += 0.2
    tp = directive.get("taxonomy_path") or []
    if isinstance(tp, list):
        score += min(len(tp), 3) * 0.033  # up to ~0.1
    return round(score, 3)


def _find_best(directives: List[Dict], vertex_type: str, motif: str, domain: str) -> List[Dict]:
    scored = []
    for d in directives:
        s = _match_score(d, vertex_type, motif, domain)
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:3]]


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def bind(topology: Dict, directives: List[Dict], default_domain: str = "general") -> Dict:
    nodes = topology.get("nodes") or []
    if not nodes:
        raise ValueError("topology.nodes must be a non-empty list")

    motif = (topology.get("metadata") or {}).get("motif", "chain")
    bindings: List[Dict] = []
    unbound: List[str] = []

    for node in nodes:
        node_id = node.get("id", "")
        vtype = node.get("vertex_type", "agent")
        domain = default_domain

        candidates = _find_best(directives, vtype, motif, domain)
        if not candidates:
            candidates = _find_best(directives, vtype, motif, "general")

        if candidates:
            bound_dirs = []
            for c in candidates[:1]:  # auto-select top 1
                bound_dirs.append({
                    "directive_id": c.get("id", ""),
                    "directive_path": c.get("_path", ""),
                    "type": c.get("type", ""),
                    "binding_rationale": f"match_score top for vertex_type={vtype}, motif={motif}",
                })
            bindings.append({
                "node_id": node_id,
                "vertex_type": vtype,
                "directives": bound_dirs,
            })
        else:
            unbound.append(node_id)

    return {
        "run_id": topology.get("run_id", ""),
        "bindings": bindings,
        "unbound_nodes": unbound,
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "registry_path": "",
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bind directives to topology nodes")
    p.add_argument("--topology", default="", help="Path to workflow_topology_spec.json")
    p.add_argument("--registry", default="", help="Path to vertex_registry directory")
    p.add_argument("--output", default="", help="Optional output path override")
    p.add_argument("--domain", default="general", help="Default domain for search")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msowd")
    p.add_argument("--case-slug", default="")
    p.add_argument("--observer-id", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    case_slug = sanitize_case_slug(args.case_slug or "binding")
    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=case_slug,
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    topo_path = Path(args.topology).expanduser().resolve() if args.topology else Path(paths["topology_path"])
    reg_path = Path(args.registry).expanduser().resolve() if args.registry else Path(paths.get("registry_path", ""))
    out = Path(args.output).expanduser().resolve() if args.output else Path(paths["bundle_path"])

    try:
        update_manifest_phase(paths, "20", "active")
        topology = json.loads(topo_path.read_text(encoding="utf-8"))

        directives = _load_registry(reg_path) if reg_path.is_dir() else []
        result = bind(topology, directives, args.domain)
        result["run_id"] = result["run_id"] or str(paths["run_id"])
        result["metadata"]["registry_path"] = str(reg_path)

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        update_manifest_phase(paths, "20", "completed")
    except Exception:
        update_manifest_phase(paths, "20", "failed")
        raise

    print(f"WROTE {out}")
    bound = len(result["bindings"])
    unbound = len(result["unbound_nodes"])
    print(f"  bound={bound}  unbound={unbound}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
