#!/usr/bin/env python3
"""
wf_node.py — Workflow node schema tool

사용법:
  python wf_node.py show <type>                                   # 스키마 출력
  python wf_node.py scaffold <type> [--id <node-id>] [--decision-subject user|agent]
  python wf_node.py validate <workflow.yaml> [--node <id>]
                            [--scaffold <root_index.yaml>]        # 검증
  python wf_node.py harness-manifest <root_workflow.yaml>
                            [--out <path>] [--format json|yaml]   # harness 집계

type: step | decision | eval | group | phase

네이밍 컨벤션(id 패턴, module 약어 등)은 프로젝트에서 정의한다.
이 스킬은 구조적 invariant 만 강제한다.

계층 참조:
- phase.workflows[].ref = "<sub_yaml>#<anchor>" 로 sub workflow 의 phase/group 참조.
- workflow_ref.module 은 scaffold module id 와 일치해야 함.
- max_depth = 3 (root + 2단계). 순환 참조 차단.
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).parent.parent / "references" / "schemas"
MAX_DEPTH = 3

DECISION_SUBJECTS = ["user", "agent"]

RESERVED_TOP_KEYS = {
    "meta", "metadata", "module", "project", "workflow",
    "dependencies", "key_decisions",
    "deliverables", "quality_metrics", "timeline",
    "versioning", "governance", "metrics",
    "milestones", "critical_dependencies",
    "feedback_loops", "success_criteria",
}


# ─── Schema loading ────────────────────────────────────────────────────────────

def load_schema(node_type: str) -> dict:
    if node_type == "oracle":
        node_type = "eval"
    path = SCHEMAS_DIR / f"{node_type}.schema.yaml"
    if not path.exists():
        sys.exit(f"[ERROR] 스키마 파일 없음: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


# ─── show ──────────────────────────────────────────────────────────────────────

def cmd_show(node_type: str):
    schema = load_schema(node_type)
    print(f"# {node_type} 노드 스키마\n")
    print(f"설명: {schema.get('description', '-')}\n")

    fields = schema.get("fields", {})
    print("## 필드")
    print(f"{'필드':<20} {'필수':<8} {'타입':<12} 설명")
    print("-" * 70)
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        required = _required_label(spec)
        ftype = spec.get("type", "-")
        if ftype == "enum":
            ftype = f"enum({', '.join(spec.get('values', []))})"
        desc = (spec.get("description", "") or "").split("\n")[0]
        print(f"  {name:<18} {required:<8} {ftype:<12} {desc}")

    if "decision_matrix" in schema:
        print("\n## Decision subject 결정 흐름")
        for i, q in enumerate(schema["decision_matrix"], 1):
            print(f"  Q{i}. {q['q']}")
            if "yes" in q:
                print(f"       YES → {q['yes']}")
            if "no" in q:
                print(f"       NO  → {q['no']}")


def _required_label(spec: dict) -> str:
    if spec.get("required") is True:
        return "필수"
    if "required_when" in spec:
        rw = spec["required_when"]
        return f"조건({rw['field']}∈{rw['values']})"
    return "선택"


# ─── scaffold ──────────────────────────────────────────────────────────────────

def cmd_scaffold(node_type: str, node_id: str | None, decision_subject: str | None):
    nid = node_id or f"TODO-{node_type}-id"

    if node_type == "step":
        node = _scaffold_step(nid)
    elif node_type == "decision":
        node = _scaffold_decision(nid, decision_subject or "agent")
    elif node_type in ("eval", "oracle", "validation"):  # v0.6.1 phase-less: validation → eval(metric)
        node = _scaffold_eval(nid)
    elif node_type == "group":
        node = _scaffold_group(nid)
    elif node_type == "phase":
        node = _scaffold_phase()
    else:
        sys.exit(f"[ERROR] 지원하지 않는 type: {node_type}")

    print(yaml.dump([node], allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip())


def _scaffold_step(node_id: str) -> dict:
    return {
        "type": "step",
        "id": node_id,
        "label": "TODO: 행위 설명",
        "status": "pending",
        "directories": [
            {"role": "input", "path": "TODO/"},
            {"role": "output", "path": "TODO/"},
        ],
        "deliverables": ["TODO"],
    }


def _scaffold_decision(node_id: str, decision_subject: str) -> dict:
    node: dict = {
        "type": "decision",
        "id": node_id,
        "label": "TODO: 분기 판단",
        "decision_subject": decision_subject,
        "decision_criteria": "TODO: 판단 기준",
    }
    if decision_subject == "user":
        node["owner"] = "TODO: owner-id"
        node["sla"] = "TODO: 응답 SLA"
        node["description"] = "TODO: 운영자가 검토할 항목 multi-line 서술"

    node["branches"] = [
        {"on": "TODO-case", "goto": "TODO-node-id"}
    ]
    return node


def _scaffold_eval(node_id: str) -> dict:
    return {
        "type": "eval",
        "id": node_id,
        "label": "TODO: 품질 평가",
        "status": "pending",
        "oracle_type": "agent",
        "evaluator": "TODO: evaluator-id",
        "criteria": ["TODO: 품질 기준"],
        "threshold": "TODO: 임계값",
        "branches": [{"on": "failed", "goto": "TODO-node-id"}],
    }


def _scaffold_group(node_id: str) -> dict:
    return {
        "type": "group",
        "id": node_id,
        "label": "TODO: 사이클 이름",
        "steps": ["# TODO: step | decision | validation | group 노드 추가"],
    }


def _scaffold_phase() -> dict:
    return {
        "id": "TODO-phase-id",
        "label": "TODO: Phase 이름",
        "status": "pending",
        "show_wrapper": True,
        "steps": ["# TODO: 노드 추가"],
        "artifacts": [],
        "success_criteria": [],
    }


# ─── Issue / ValidationError ──────────────────────────────────────────────────

class ValidationError:
    def __init__(self, node_id: str, field: str, message: str, level: str = "error"):
        self.node_id = node_id
        self.field = field
        self.message = message
        self.level = level

    def __str__(self):
        tag = "ERROR" if self.level == "error" else "WARN "
        return f"  [{tag}] {self.node_id} / {self.field}: {self.message}"


# ─── YAML 로드 ────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        raise RuntimeError(f"YAML 파싱 실패: {path}: {e}")


# ─── scaffold(index.yaml) 로컬 resolver — wf_node 독립 구현 ───────────────────
# v1: 두 스킬에 동일 로직 중복 (사용자 결정). cross-skill invariant 검증용.

def _resolve_scaffold(root_yaml: Path, max_depth: int = MAX_DEPTH) -> dict:
    """scaffold root index.yaml 을 계층 평탄화. (sf_node.resolve_tree 의 간소 사본)

    project.root_offset 지원 (예: "../..") — yaml 위치와 다른 프로젝트 루트.

    Returns: {
        "project_id": str | None,
        "module_ids": set[str],
        "module_paths": dict[str, Path],   # id → 절대 fs path
        "fs_root": Path,
        "issues": list[str],
    }
    """
    out = {
        "project_id": None,
        "module_ids": set(),
        "module_paths": {},
        "fs_root": None,
        "issues": [],
    }
    root_doc = _load_yaml(root_yaml)
    if root_doc is None:
        out["issues"].append(f"scaffold 파일 로드 실패: {root_yaml}")
        return out
    out["project_id"] = (root_doc.get("project") or {}).get("id")

    root_offset = (root_doc.get("project") or {}).get("root_offset")
    if root_offset:
        fs_root = (root_yaml.parent / root_offset).resolve()
    else:
        fs_root = root_yaml.parent.resolve()
    out["fs_root"] = fs_root

    visited: set[Path] = {root_yaml.resolve()}
    _recurse_scaffold(root_doc, root_yaml.resolve(), fs_root,
                      1, max_depth, visited, out)
    return out


def _recurse_scaffold(doc, source: Path, fs_root: Path, depth: int,
                      max_depth: int, visited: set, out: dict):
    for m in doc.get("modules", []) or []:
        mid = m.get("id")
        mpath = m.get("path", "")
        mod_fs = (fs_root / mpath).resolve() if mpath else fs_root
        if mid:
            out["module_ids"].add(mid)
            out["module_paths"][mid] = mod_fs
        sub_rel = m.get("sub_index")
        if not sub_rel:
            continue
        if depth + 1 > max_depth:
            out["issues"].append(f"scaffold max_depth({max_depth}) 초과: module:{mid}")
            continue
        sub_path = (fs_root / sub_rel).resolve()
        if sub_path in visited or not sub_path.exists():
            continue
        visited.add(sub_path)
        sub_doc = _load_yaml(sub_path)
        if sub_doc is None:
            continue
        _recurse_scaffold(sub_doc, sub_path, mod_fs, depth + 1, max_depth, visited, out)


# ─── workflow tree resolver ───────────────────────────────────────────────────

class ResolvedWorkflow:
    def __init__(self):
        self.root_source: Path | None = None
        self.docs: dict[Path, dict] = {}              # source path → doc
        self.refs: list[dict] = []                    # ref 진입점 추적용
        self.issues: list[ValidationError] = []
        self.all_node_ids: list[tuple[str, Path]] = []  # (node_id, source)
        self.validation_nodes: list[tuple[dict, Path, str | None]] = []
        # (node, source, module_id_hint)


def resolve_workflow_tree(root_yaml: Path, max_depth: int = MAX_DEPTH) -> ResolvedWorkflow:
    """root workflow YAML 에서 phase.workflows[].ref 를 따라가며 sub 트리 평탄화."""
    resolved = ResolvedWorkflow()
    resolved.root_source = root_yaml.resolve()

    root_doc = _load_yaml(root_yaml)
    if root_doc is None:
        resolved.issues.append(ValidationError("(root)", "file",
                                               f"파일 없음 또는 빈 yaml: {root_yaml}"))
        return resolved
    # visited 는 (path, anchor) 튜플 — 같은 파일의 다른 anchor 진입은 허용
    visited: set[tuple[Path, str]] = {(root_yaml.resolve(), "")}
    _recurse_workflow(root_doc, root_yaml.resolve(), 1, max_depth, visited, resolved,
                      module_id_hint=(root_doc.get("module") or {}).get("id"))
    return resolved


def _recurse_workflow(doc, source: Path, depth: int, max_depth: int,
                      visited: set, resolved: ResolvedWorkflow,
                      module_id_hint: str | None):
    # 한 파일은 한 번만 docs 에 기록 (anchor 별 중복 로드는 동일 내용)
    if source not in resolved.docs:
        resolved.docs[source] = doc

        for phase_key, phase in _collect_phases(doc):
            if not isinstance(phase, dict):
                continue
            for nid in _collect_node_ids(phase.get("steps", []) or []):
                resolved.all_node_ids.append((nid, source))
            for vn in _collect_validations(phase.get("steps", []) or []):
                resolved.validation_nodes.append((vn, source, module_id_hint))

    # workflows[] 참조 따라가기 (anchor 별)
    for phase_key, phase in _collect_phases(doc):
        if not isinstance(phase, dict):
            continue
        for ref_obj in phase.get("workflows", []) or []:
            if not isinstance(ref_obj, dict):
                continue
            resolved.refs.append({"ref": ref_obj, "source": source, "phase": phase_key})
            ref_str = ref_obj.get("ref", "")
            if not ref_str:
                continue
            ref_path_str, _, anchor = ref_str.partition("#")
            sub_path = (source.parent / ref_path_str).resolve()
            if depth + 1 > max_depth:
                resolved.issues.append(ValidationError(
                    f"phase:{phase_key}", "workflows.ref",
                    f"max_depth({max_depth}) 초과: 현재 depth={depth+1}"
                ))
                continue
            key = (sub_path, anchor)
            if key in visited:
                # 같은 (path, anchor) 재방문만 순환으로 간주
                continue
            if not sub_path.exists():
                resolved.issues.append(ValidationError(
                    f"phase:{phase_key}", "workflows.ref",
                    f"sub workflow 파일 없음: {sub_path}"
                ))
                continue
            visited.add(key)
            sub_doc = _load_yaml(sub_path)
            if sub_doc is None:
                continue
            sub_module_id = (sub_doc.get("module") or {}).get("id")
            _recurse_workflow(sub_doc, sub_path, depth + 1, max_depth,
                              visited, resolved, module_id_hint=sub_module_id)


def _collect_phases(doc: dict) -> list[tuple[str, dict]]:
    if not isinstance(doc, dict):
        return []
    out = []
    for key, val in doc.items():
        if key in RESERVED_TOP_KEYS:
            continue
        if key.startswith("x_") or key.startswith("x-"):
            continue  # 확장 네임스페이스(OpenAPI x- 패턴) — 소비자(MSM 등) 도메인 필드. phase 아님.
        if isinstance(val, dict):
            out.append((key, val))
    return out


def _collect_node_ids(nodes: list) -> list[str]:
    out = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid:
            out.append(nid)
        if n.get("type") == "group":
            out.extend(_collect_node_ids(n.get("steps", []) or []))
    return out


def _collect_validations(nodes: list) -> list[dict]:
    # v0.6.1 phase-less: validation 폐지 → harness 필드를 가진 노드(eval[metric] 등)를 수집.
    # cmd_harness_manifest 가 type 무관하게 harness 게이트를 모은다.
    out = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("harness"):
            out.append(n)
        if n.get("type") == "group":
            out.extend(_collect_validations(n.get("steps", []) or []))
    return out


def _collect_phase_group_ids(doc: dict) -> set[str]:
    """anchor 검증용 — sub 파일 내 phase id + group id 집합."""
    ids = set()
    for key, _ in _collect_phases(doc):
        ids.add(key)
    for _, phase in _collect_phases(doc):
        for n in _walk_nodes(phase.get("steps", []) or []):
            if n.get("type") == "group" and n.get("id"):
                ids.add(n["id"])
    return ids


def _walk_nodes(nodes: list):
    for n in nodes:
        if not isinstance(n, dict):
            continue
        yield n
        if n.get("type") == "group":
            yield from _walk_nodes(n.get("steps", []) or [])


# ─── validate ─────────────────────────────────────────────────────────────────

def cmd_validate(workflow_path: str, target_node_id: str | None = None,
                 scaffold_path: str | None = None):
    path = Path(workflow_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 없음: {workflow_path}")

    # 계층 해석
    resolved = resolve_workflow_tree(path)
    errors: list[ValidationError] = list(resolved.issues)

    # scaffold 옵션이 있으면 cross-skill 검증 준비
    scaffold_resolved = None
    if scaffold_path:
        spath = Path(scaffold_path)
        if not spath.exists():
            sys.exit(f"[ERROR] scaffold 파일 없음: {scaffold_path}")
        scaffold_resolved = _resolve_scaffold(spath)
        for msg in scaffold_resolved.get("issues", []):
            errors.append(ValidationError("(scaffold)", "load", msg))

    # 각 sub doc 단일 스키마 검증
    for src, doc in resolved.docs.items():
        errors.extend(_validate_single_doc(doc, src, target_node_id))

    # 전역 노드 id unique
    seen: dict[str, list[Path]] = {}
    for nid, src in resolved.all_node_ids:
        seen.setdefault(nid, []).append(src)
    for nid, srcs in seen.items():
        if len(srcs) > 1:
            uniq_srcs = ", ".join({s.name for s in srcs})
            errors.append(ValidationError(nid, "id",
                                          f"전역 중복 id (sources: {uniq_srcs})"))

    # workflow_ref 검증
    errors.extend(_validate_workflow_refs(resolved, scaffold_resolved))

    # cross-skill: directories.path / dependencies
    if scaffold_resolved is not None:
        errors.extend(_validate_cross_skill(resolved, scaffold_resolved))

    _print_results(errors, workflow_path)
    return len([e for e in errors if e.level == "error"]) == 0


def _validate_single_doc(doc: dict, source: Path,
                         target_node_id: str | None) -> list[ValidationError]:
    """단일 workflow doc 의 phase / 노드 구조적 검증."""
    errors: list[ValidationError] = []

    phase_entries = _collect_phases(doc)
    if not phase_entries:
        errors.append(ValidationError(f"({source.name})", "phases",
                                       "phase 가 하나도 없음"))

    for phase_key, phase in phase_entries:
        errors.extend(_validate_phase(phase_key, phase, source))
        node_errors = _validate_nodes(phase.get("steps", []) or [], target_node_id)
        errors.extend(node_errors)

    return errors


def _validate_phase(phase_id: str, phase: dict, source: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    ctx = f"phase:{phase_id} @ {source.name}"

    if not isinstance(phase, dict):
        errors.append(ValidationError(ctx, "(phase)", "phase 가 dict 아님"))
        return errors

    if not phase.get("label"):
        errors.append(ValidationError(ctx, "label", "필수 필드 없음"))

    status = phase.get("status")
    allowed_status = ["completed", "active", "pending"]
    if not status:
        errors.append(ValidationError(ctx, "status", "필수 필드 없음"))
    elif status not in allowed_status:
        errors.append(ValidationError(ctx, "status",
                                       f"허용값 아님: {status} (허용: {allowed_status})"))

    has_steps = bool(phase.get("steps"))
    has_workflows = bool(phase.get("workflows"))
    has_artifacts = bool(phase.get("artifacts"))
    if not has_steps and not has_workflows and not has_artifacts:
        errors.append(ValidationError(ctx, "steps|workflows|artifacts",
                                       "steps / workflows / artifacts 중 하나는 필요"))

    ds = phase.get("default_decision_subject")
    if ds and ds not in DECISION_SUBJECTS:
        errors.append(ValidationError(ctx, "default_decision_subject", f"허용값 아님: {ds}"))

    return errors


def _validate_nodes(nodes: list, target_id: str | None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        node_id = node.get("id", "(no-id)")

        if target_id and node_id != target_id:
            if node_type == "group":
                errors.extend(_validate_nodes(node.get("steps", []) or [], target_id))
            continue

        if node_type == "step":
            errors.extend(_validate_step(node_id, node))
        elif node_type == "decision":
            errors.extend(_validate_decision(node_id, node))
        elif node_type == "validation":
            errors.extend(_validate_validation(node_id, node))
        elif node_type in ("eval", "oracle"):
            errors.extend(_validate_eval(node_id, node))
        elif node_type == "group":
            errors.extend(_validate_group(node_id, node))
            errors.extend(_validate_nodes(node.get("steps", []) or [], target_id))
        else:
            errors.append(ValidationError(node_id, "type", f"알 수 없는 type: {node_type}"))

    return errors


def _validate_step(node_id: str, node: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for fname in ["id", "label", "status"]:
        if not node.get(fname):
            errors.append(ValidationError(node_id, fname, "필수 필드 없음"))

    status = node.get("status")
    allowed_status = ["completed", "active", "pending"]
    if status and status not in allowed_status:
        errors.append(ValidationError(node_id, "status",
                                       f"허용값 아님: {status} (허용: {allowed_status})"))

    dirs = node.get("directories", [])
    if dirs:
        for d in dirs:
            if not d.get("role"):
                errors.append(ValidationError(node_id, "directories.role", "role 없음"))
            if not d.get("path"):
                errors.append(ValidationError(node_id, "directories.path", "path 없음"))
    return errors


def _validate_decision(node_id: str, node: dict) -> list[ValidationError]:
    schema = load_schema("decision")
    errors: list[ValidationError] = []
    decision_subject = node.get("decision_subject")

    for fname in ["id", "label", "decision_subject"]:
        if not node.get(fname):
            errors.append(ValidationError(node_id, fname, "필수 필드 없음"))

    if not decision_subject:
        return errors

    allowed_subjects = schema["fields"]["decision_subject"]["values"]
    if decision_subject not in allowed_subjects:
        errors.append(ValidationError(node_id, "decision_subject",
                                       f"허용값 아님: {decision_subject} (허용: {allowed_subjects})"))
        return errors

    # PyYAML 1.1: unquoted `on:` → True. 값은 routing case 이므로 비어 있으면 안 된다.
    branches = node.get("branches", [])
    for branch in branches:
        on_val = branch.get("on", branch.get(True))
        if on_val in (None, ""):
            errors.append(ValidationError(node_id, "branches.on", "routing case 비어있음"))
    return errors


def _validate_validation(node_id: str, node: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for fname in ["id", "label", "status", "harness", "pass_criteria"]:
        if not node.get(fname):
            errors.append(ValidationError(node_id, fname, "필수 필드 없음"))

    status = node.get("status")
    allowed_status = ["completed", "active", "pending"]
    if status and status not in allowed_status:
        errors.append(ValidationError(node_id, "status",
                                       f"허용값 아님: {status} (허용: {allowed_status})"))

    on_fail = node.get("on_fail")
    allowed_on_fail = ["block", "retry", "manual_review"]
    if on_fail and on_fail not in allowed_on_fail:
        errors.append(ValidationError(node_id, "on_fail",
                                       f"허용값 아님: {on_fail} (허용: {allowed_on_fail})"))

    pc = node.get("pass_criteria")
    if pc is not None and not isinstance(pc, list):
        errors.append(ValidationError(node_id, "pass_criteria", "list 형식이어야 함"))
    elif isinstance(pc, list) and len(pc) == 0:
        errors.append(ValidationError(node_id, "pass_criteria", "최소 1개 이상"))

    return errors


def _validate_eval(node_id: str, node: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for fname in ["id", "label", "status", "oracle_type", "criteria"]:
        if not node.get(fname):
            errors.append(ValidationError(node_id, fname, "필수 필드 없음"))

    status = node.get("status")
    allowed_status = ["completed", "active", "pending"]
    if status and status not in allowed_status:
        errors.append(ValidationError(node_id, "status",
                                       f"허용값 아님: {status} (허용: {allowed_status})"))

    oracle_type = node.get("oracle_type")
    allowed_oracle_types = ["user", "agent", "metric"]
    if oracle_type and oracle_type not in allowed_oracle_types:
        errors.append(ValidationError(node_id, "oracle_type",
                                       f"허용값 아님: {oracle_type} (허용: {allowed_oracle_types})"))

    criteria = node.get("criteria")
    if criteria is not None and not isinstance(criteria, list):
        errors.append(ValidationError(node_id, "criteria", "list 형식이어야 함"))
    elif isinstance(criteria, list) and len(criteria) == 0:
        errors.append(ValidationError(node_id, "criteria", "최소 1개 이상"))

    on_fail = node.get("on_fail")
    allowed_on_fail = ["block", "retry", "manual_review"]
    if on_fail and on_fail not in allowed_on_fail:
        errors.append(ValidationError(node_id, "on_fail",
                                       f"허용값 아님: {on_fail} (허용: {allowed_on_fail})"))
    return errors


def _validate_group(node_id: str, node: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not node.get("id"):
        errors.append(ValidationError(node_id, "id", "필수 필드 없음"))
    if not node.get("label"):
        errors.append(ValidationError(node_id, "label", "필수 필드 없음"))
    if not node.get("steps"):
        errors.append(ValidationError(node_id, "steps", "group에 steps 없음", "warning"))
    return errors


def _validate_workflow_refs(resolved: ResolvedWorkflow,
                            scaffold_resolved: dict | None) -> list[ValidationError]:
    """phase.workflows[].ref / module / anchor 검증."""
    errors: list[ValidationError] = []
    for entry in resolved.refs:
        ref_obj = entry["ref"]
        source = entry["source"]
        phase_key = entry["phase"]
        ctx = f"phase:{phase_key} @ {source.name}"

        ref_str = ref_obj.get("ref")
        mod_id = ref_obj.get("module")
        if not ref_str:
            errors.append(ValidationError(ctx, "workflows.ref", "필수 필드 없음"))
            continue
        if not mod_id:
            errors.append(ValidationError(ctx, "workflows.module", "필수 필드 없음"))

        ref_file, _, anchor = ref_str.partition("#")
        sub_path = (source.parent / ref_file).resolve()
        if not sub_path.exists():
            errors.append(ValidationError(ctx, "workflows.ref",
                                           f"sub workflow 파일 없음: {sub_path}"))
            continue

        sub_doc = resolved.docs.get(sub_path) or _load_yaml(sub_path)
        if sub_doc is None:
            continue

        # module 일치 검사 — sub 파일이 선언한 module.id 와 일치
        sub_decl_mod = (sub_doc.get("module") or {}).get("id")
        if mod_id and sub_decl_mod and mod_id != sub_decl_mod:
            errors.append(ValidationError(
                ctx, "workflows.module",
                f"ref 파일의 module.id={sub_decl_mod} 와 불일치 (선언={mod_id})"
            ))

        # anchor 유효성
        if anchor:
            allowed_anchors = _collect_phase_group_ids(sub_doc)
            if anchor not in allowed_anchors:
                errors.append(ValidationError(
                    ctx, "workflows.ref.anchor",
                    f"anchor '{anchor}' 가 sub 파일에 없음 (사용 가능: {sorted(allowed_anchors)})"
                ))

        # scaffold cross-check
        if scaffold_resolved is not None and mod_id:
            if mod_id not in scaffold_resolved["module_ids"]:
                errors.append(ValidationError(
                    ctx, "workflows.module",
                    f"scaffold 에 없는 module id: {mod_id}"
                ))
            else:
                mod_fs = scaffold_resolved["module_paths"].get(mod_id)
                if mod_fs:
                    try:
                        sub_path.relative_to(mod_fs)
                    except ValueError:
                        errors.append(ValidationError(
                            ctx, "workflows.ref",
                            f"sub workflow 파일이 module path 의 자손 아님: {sub_path} ∉ {mod_fs}/"
                        ))
    return errors


def _validate_cross_skill(resolved: ResolvedWorkflow,
                          scaffold_resolved: dict) -> list[ValidationError]:
    """directories.path ∈ scaffold 등록 경로, dependencies.source ∈ scaffold module ids."""
    errors: list[ValidationError] = []

    def _nfc(p: Path) -> str:
        return unicodedata.normalize("NFC", str(p.resolve()))

    # scaffold 의 모든 declared paths (모듈 fs root 합집합)
    declared_roots = {_nfc(p) for p in scaffold_resolved["module_paths"].values()}
    module_ids = scaffold_resolved["module_ids"]

    for src, doc in resolved.docs.items():
        for phase_key, phase in _collect_phases(doc):
            for n in _walk_nodes(phase.get("steps", []) or []):
                for d in n.get("directories", []) or []:
                    p = d.get("path")
                    if not p:
                        continue
                    # 절대화: workflow 파일 위치 기준
                    p_abs = _nfc((src.parent / p).resolve())
                    # workflow 의 directories.path 는 scaffold 의 어떤 모듈 fs root 의 자손이어야 함
                    matched = any(p_abs.startswith(root + "/") or p_abs == root
                                  for root in declared_roots)
                    if not matched:
                        errors.append(ValidationError(
                            n.get("id", "?"), "directories.path",
                            f"scaffold 미등록 경로: {p}", "warning"
                        ))

        # dependencies
        for dep in doc.get("dependencies", []) or []:
            src_mod = dep.get("source")
            if src_mod and src_mod not in module_ids and src_mod != "internal":
                errors.append(ValidationError(
                    f"dependencies @ {src.name}", "source",
                    f"scaffold 에 없는 module id: {src_mod}", "warning"
                ))
            for tgt in dep.get("consumers", []) or []:
                if tgt not in module_ids:
                    errors.append(ValidationError(
                        f"dependencies @ {src.name}", "consumers",
                        f"scaffold 에 없는 module id: {tgt}", "warning"
                    ))
    return errors


def _print_results(errors: list[ValidationError], path: str):
    err_count = len([e for e in errors if e.level == "error"])
    warn_count = len([e for e in errors if e.level == "warning"])

    print(f"\n검증: {path}")
    print(f"결과: ERROR {err_count}개, WARNING {warn_count}개\n")

    if not errors:
        print("  ✓ 모든 노드가 스키마를 준수합니다.")
        return

    for e in errors:
        icon = "✗" if e.level == "error" else "△"
        print(f"  {icon} {e}")

    if err_count > 0:
        print(f"\n→ {err_count}개 오류를 수정 후 재실행하세요.")
    else:
        print(f"\n→ WARNING만 있습니다. 계속 진행 가능합니다.")


# ─── harness-manifest ─────────────────────────────────────────────────────────

def cmd_harness_manifest(workflow_path: str, out: str | None, fmt: str = "json"):
    """root workflow 부터 sub 까지 validation 노드의 harness 를 모아 manifest 생성."""
    path = Path(workflow_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 없음: {workflow_path}")

    resolved = resolve_workflow_tree(path)
    manifest: list[dict] = []

    for node, src, mod_id in resolved.validation_nodes:
        entry = {
            "node_id": node.get("id"),
            "label": node.get("label"),
            "harness": node.get("harness"),
            "pass_criteria": node.get("pass_criteria", []),
            "on_fail": node.get("on_fail", "block"),
            "status": node.get("status"),
            "source_file": str(src),
            "module": mod_id,
        }
        manifest.append(entry)

    # harness runner id 중복 WARN
    counts: dict[str, int] = {}
    for e in manifest:
        h = e.get("harness")
        if h:
            counts[h] = counts.get(h, 0) + 1
    warnings = [f"harness '{h}' 가 {c}개 노드에 등장 (의도 확인)"
                for h, c in counts.items() if c > 1]

    payload = {
        "root_workflow": str(path),
        "total": len(manifest),
        "entries": manifest,
        "warnings": warnings,
    }

    if fmt == "yaml":
        rendered = yaml.dump(payload, allow_unicode=True, sort_keys=False)
    else:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)

    if out:
        Path(out).write_text(rendered)
        print(f"✓ harness manifest 저장: {out} ({len(manifest)} 노드)")
    else:
        print(rendered)


# ─── validate-all (다중 workflow) ─────────────────────────────────────────────

def cmd_validate_all(dir_path: str, pattern: str = "workflow*.yaml",
                     scaffold_path: str | None = None) -> int:
    """디렉토리 안 모든 workflow YAML 일괄 검증.

    명명 컨벤션: `workflow-<slug>.yaml` (예: workflow-lifecycle.yaml, workflow-release.yaml).
    각 YAML 은 독립 root 로 간주, 각자 sub workflow tree 해석.
    """
    base = Path(dir_path)
    if not base.is_dir():
        print(f"[ERROR] 디렉토리 아님: {dir_path}", file=sys.stderr)
        return 1

    yamls = sorted(p for p in base.glob(pattern) if p.is_file())
    if not yamls:
        print(f"[WARN] 매칭되는 파일 없음: {base}/{pattern}", file=sys.stderr)
        return 0

    print(f"\nValidate-all: {base} (pattern={pattern}, {len(yamls)} files)\n")
    failed = 0
    for yml in yamls:
        print(f"─── {yml.name} ───")
        ok = cmd_validate(str(yml), None, scaffold_path)
        if not ok:
            failed += 1
        print()
    print(f"=== Summary: {len(yamls) - failed}/{len(yamls)} passed ===")
    return 1 if failed else 0


# ─── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Workflow node schema tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="노드 유형 스키마 출력")
    p_show.add_argument("type", choices=["step", "decision", "validation", "eval", "oracle", "group", "phase"])

    p_sc = sub.add_parser("scaffold", help="노드 스캐폴드 YAML 생성")
    p_sc.add_argument("type", choices=["step", "decision", "validation", "eval", "oracle", "group", "phase"])
    p_sc.add_argument("--id", dest="node_id", default=None,
                      help="노드 id (생략 시 placeholder). 네이밍 패턴은 프로젝트 컨벤션.")
    p_sc.add_argument("--decision-subject", choices=DECISION_SUBJECTS,
                      help="decision 판단 주체(user|agent)")

    p_val = sub.add_parser("validate", help="워크플로우 YAML 검증 (계층 자동 해석)")
    p_val.add_argument("workflow", help="검증할 workflow YAML 파일 경로")
    p_val.add_argument("--node", help="특정 node id만 검증")
    p_val.add_argument("--scaffold", help="cross-skill 검증용 scaffold root index.yaml")

    p_har = sub.add_parser("harness-manifest", help="validation 노드 harness 집계")
    p_har.add_argument("workflow", help="root workflow YAML 경로")
    p_har.add_argument("--out", help="출력 파일 (생략 시 stdout)")
    p_har.add_argument("--format", choices=["json", "yaml"], default="json")

    p_va = sub.add_parser("validate-all", help="디렉토리 내 모든 workflow*.yaml 일괄 검증")
    p_va.add_argument("dir", help="workflow YAML 들이 모여있는 디렉토리")
    p_va.add_argument("--scaffold", help="cross-skill 검증용 scaffold root index.yaml")
    p_va.add_argument("--pattern", default="workflow*.yaml",
                      help="glob 패턴 (default: workflow*.yaml). 모듈 workflow 도 포함하려면 '*workflow*.yaml'")

    args = parser.parse_args()

    if args.cmd == "show":
        cmd_show(args.type)
    elif args.cmd == "scaffold":
        cmd_scaffold(args.type, args.node_id, getattr(args, "decision_subject", None))
    elif args.cmd == "validate":
        ok = cmd_validate(args.workflow, getattr(args, "node", None),
                          getattr(args, "scaffold", None))
        sys.exit(0 if ok else 1)
    elif args.cmd == "harness-manifest":
        cmd_harness_manifest(args.workflow, args.out, args.format)
    elif args.cmd == "validate-all":
        rc = cmd_validate_all(args.dir, args.pattern, getattr(args, "scaffold", None))
        sys.exit(rc)


if __name__ == "__main__":
    main()
