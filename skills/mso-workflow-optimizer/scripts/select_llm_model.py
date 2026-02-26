#!/usr/bin/env python3
"""List or validate provider/model choices from llm-model-catalog.yaml.

Examples:
  python3 {mso-workflow-optimizer}/scripts/select_llm_model.py --provider openai
  python3 {mso-workflow-optimizer}/scripts/select_llm_model.py --provider anthropic --model claude-sonnet-4-5 --emit-env
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"[error] PyYAML is required: {exc}", file=sys.stderr)
    sys.exit(2)


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "llm-model-catalog.yaml"


def _load_catalog(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("catalog root must be a mapping")
    return data


def _providers(catalog: Dict[str, Any]) -> Dict[str, Any]:
    providers = catalog.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("providers must be a mapping")
    return providers


def _model_ids(provider_data: Dict[str, Any]) -> List[str]:
    items = provider_data.get("recommended_for_analysis", [])
    out: List[str] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid.strip():
                out.append(mid.strip())
    return out


def _print_provider(name: str, pdata: Dict[str, Any]) -> None:
    default_model = pdata.get("recommended_default_model", "")
    print(f"[{name}] default={default_model}")
    for item in pdata.get("recommended_for_analysis", []):
        if not isinstance(item, dict):
            continue
        model_id = item.get("id", "")
        fit = item.get("analysis_fit", "")
        why = item.get("why", "")
        print(f"  - {model_id} ({fit})")
        print(f"    {why}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select LLM model options for mso-workflow-optimizer")
    parser.add_argument("--provider", choices=["openai", "anthropic", "google", "all"], default="all")
    parser.add_argument("--model", help="Validate a model id for a provider")
    parser.add_argument("--emit-env", action="store_true", help="Print export commands if provider/model is valid")
    parser.add_argument("--json", action="store_true", help="Print selected data as JSON")
    args = parser.parse_args()

    catalog = _load_catalog(_catalog_path())
    providers = _providers(catalog)

    selected_names = list(providers.keys()) if args.provider == "all" else [args.provider]
    for name in selected_names:
        if name not in providers:
            print(f"[error] unknown provider: {name}", file=sys.stderr)
            return 1

    if args.model:
        if args.provider == "all":
            print("[error] --model requires a concrete --provider", file=sys.stderr)
            return 1
        ids = _model_ids(providers[args.provider])
        if args.model not in ids:
            print(f"[error] model '{args.model}' not found for provider '{args.provider}'", file=sys.stderr)
            print(f"[hint] available: {', '.join(ids)}", file=sys.stderr)
            return 1
        if args.emit_env:
            print(f"export LLM_API_PROVIDER={args.provider}")
            print(f"export LLM_MODEL={args.model}")
        else:
            print(f"valid: provider={args.provider}, model={args.model}")
        return 0

    if args.json:
        payload = {name: providers[name] for name in selected_names}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for name in selected_names:
        _print_provider(name, providers[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
