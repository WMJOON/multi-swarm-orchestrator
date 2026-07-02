#!/usr/bin/env python3
"""validate_abox — TTL ABox(SSOT-of-record) 직접 검증 진입점.

wf_to_ttl.py 의 validate 는 legacy YAML migration 경로 전용이다.
이 스크립트는 정본인 `*.abox.ttl` 을 직접 파싱해 검증한다.
v0.6 어휘와 v0.7 Rail/Stream 어휘를 파일 단위로 자동 감지해 각 스택으로 검증한다.

v0.6 스택:
  1) SHACL 로컬 shape        — references/shapes/workflow-shapes.ttl
  2) Feedback-loop control   — Eval/user/deterministic Decision 없는 순환 (SPARQL)
  3) Eval targetArtifact     — target workflow 생산물과의 정합
  4) Directory shape         — wf:directory 노드의 dirPath/dirRole 필수
  5) Step multi-outgoing     — Step 이 제어 edge 2개 이상 → Decision 모델링 경고

v0.7-r2 스택 (SPEC §6-B, D-13~D-16):
  1) SHACL v07 shape         — references/shapes/workflow-shapes-v07.ttl
                               (Start/End·Task out=1·Decision branch≥2·hand_off 주체·
                                Eval measured_by/measures/fail/pass·oracle-only·Stream bipartite)
  2) Oracle disjoint         — evolves_to/tests_to 대상과 소속 workflow의 조상/자손 금지
  3) Task partition          — 서로 다른 Workflow의 Task 공유 금지
  4) Feedback-loop control   — default Rail 순환 내 EvalTask/user·criteria DecisionTask 필수

공통: legacy YAML 잔존 경고. SSOT 거버넌스 판정은 이 스킬(mso-workflow-design)이
소유하며, 관측 스킬(mso-graph-observability)은 판정 없이 리포트로 렌더만 한다.

Usage:
  python validate_abox.py <path.abox.ttl | workflow-dir> [...] [--json] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from rdflib import Graph, Literal, RDF, URIRef
except ImportError as exc:  # pragma: no cover - user environment guard
    raise SystemExit("rdflib is required: pip install rdflib") from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_to_ttl import (  # noqa: E402
    WF,
    find_eval_target_artifact_mismatches,
    find_uncontrolled_loops,
    run_shacl,
)
from wf_v07 import execution_subject, is_v07_graph  # noqa: E402

SHAPES_V07 = Path(__file__).resolve().parent.parent / "references" / "shapes" / "workflow-shapes-v07.ttl"


def collect_abox_paths(targets: list[Path]) -> list[Path]:
    """명시 파일 + 디렉토리 재귀의 *.abox.ttl 목록."""
    paths: list[Path] = []
    for target in targets:
        if target.is_dir():
            paths.extend(sorted(target.rglob("*.abox.ttl")))
        elif target.suffix == ".ttl":
            paths.append(target)
    seen: set[Path] = set()
    unique = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def parse_graph(paths: list[Path]) -> Graph:
    g = Graph()
    for path in paths:
        g.parse(str(path), format="turtle")
    return g


# ═══════════════════════════════ v0.6 검사 ═══════════════════════════════


def find_directory_shape_issues(g: Graph) -> list[str]:
    """wf:directory 노드는 wf:dirPath + wf:dirRole 필수 (blank node라 SHACL targetClass 미적용)."""
    issues: list[str] = []
    seen: set[str] = set()
    for node, directory in g.subject_objects(WF.directory):
        key = f"{node}|{directory}"
        if key in seen:
            continue
        seen.add(key)
        missing = []
        if not isinstance(g.value(directory, WF.dirPath), Literal):
            missing.append("wf:dirPath")
        if not isinstance(g.value(directory, WF.dirRole), Literal):
            missing.append("wf:dirRole")
        if missing:
            node_id = str(node).rsplit("/", 1)[-1]
            issues.append(f"directory shape: {node_id} 의 wf:directory 에 {', '.join(missing)} 누락")
    return issues


def find_step_multi_outgoing(g: Graph) -> list[str]:
    """Step 이 제어 edge(next/branch goto) 2개 이상이면 Decision 으로 모델링해야 한다 (warning)."""
    warnings: list[str] = []
    for step in sorted(g.subjects(RDF.type, WF.Step), key=str):
        if (step, RDF.type, WF.Decision) in g or (step, RDF.type, WF.Eval) in g:
            continue
        targets: set[str] = set()
        for nxt in g.objects(step, WF.next):
            if isinstance(nxt, URIRef):
                targets.add(str(nxt))
        for branch in g.objects(step, WF.hasBranch):
            for goto in g.objects(branch, WF.gotoNode):
                targets.add(str(goto))
            for goto in g.objects(branch, WF.goto):
                targets.add(str(goto))
        if len(targets) >= 2:
            step_id = str(step).rsplit("/", 1)[-1]
            warnings.append(
                f"step multi-outgoing: {step_id} 이(가) 제어 edge {len(targets)}개 — "
                "분기는 wf:Decision + wf:hasBranch(2개 이상)로 모델링 권장"
            )
    return warnings


# ═══════════════════════════════ v0.7 검사 ═══════════════════════════════


def run_shacl_v07(g: Graph) -> tuple[bool, str]:
    try:
        from pyshacl import validate as shacl_validate
    except ImportError:
        return True, "[skip] pyshacl 미설치 — v07 shape 검증 생략"
    shapes = Graph().parse(str(SHAPES_V07), format="turtle")
    conforms, _, text = shacl_validate(
        g, shacl_graph=shapes, inference="none", advanced=True, meta_shacl=False,
    )
    return conforms, text


def _sub_workflow_connected(g: Graph, a: URIRef, b: URIRef) -> bool:
    """a와 b가 has_subWorkflow* 로 조상/자손 관계인지 (동일 포함)."""
    if a == b:
        return True
    for start, goal in ((a, b), (b, a)):
        frontier = [start]
        seen = set()
        while frontier:
            current = frontier.pop()
            if current == goal:
                return True
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(
                child for child in g.objects(current, WF.has_subWorkflow)
                if isinstance(child, URIRef)
            )
    return False


def find_oracle_disjoint_violations_v07(g: Graph) -> tuple[list[str], list[str]]:
    """oracle rail(evolves_to/tests_to) 대상 정합 (D-10①, D-12).

    - Workflow 대상: 소속 workflow와 has_subWorkflow* 조상/자손 금지 (오류)
    - Artifact 대상 (D-12):
      ① oracle workflow 자신이 생산한 artifact evolve 금지 — 자기 증거 조작 루프 (오류)
      ② 어떤 Task/Executor도 소비하지 않는 artifact evolve — 정당화 근거 없음 (경고)
    반환: (issues, warnings)
    """
    issues: list[str] = []
    warnings: list[str] = []

    def _owner_produced_artifacts(owner: URIRef) -> set[URIRef]:
        """owner workflow의 member(및 member가 위임한 Executor)가 생산하는 artifact."""
        members = {n for n in g.objects(owner, WF.has) if isinstance(n, URIRef)}
        producers = set(members)
        for member in members:
            for deleg_rail in g.subjects(RDF.type, WF.Rail):
                if g.value(deleg_rail, WF.railType) == Literal("delegates_to") and \
                        g.value(deleg_rail, WF["from"]) == member:
                    executor = g.value(deleg_rail, WF.to)
                    if isinstance(executor, URIRef):
                        producers.add(executor)
        produced: set[URIRef] = set()
        for stream in g.subjects(RDF.type, WF.Stream):
            if g.value(stream, WF.streamType) != Literal("produces_to"):
                continue
            if g.value(stream, WF["from"]) in producers:
                artifact = g.value(stream, WF.to)
                if isinstance(artifact, URIRef):
                    produced.add(artifact)
        return produced

    def _artifact_consumed_anywhere(artifact: URIRef) -> bool:
        for stream in g.subjects(RDF.type, WF.Stream):
            if g.value(stream, WF.streamType) == Literal("consumed_by") and \
                    g.value(stream, WF["from"]) == artifact:
                return True
        for rail in g.subjects(RDF.type, WF.Rail):
            if g.value(rail, WF.railType) == Literal("reads") and \
                    g.value(rail, WF["from"]) == artifact:
                return True
        return False

    for rail in g.subjects(RDF.type, WF.Rail):
        rail_type = g.value(rail, WF.railType)
        if not isinstance(rail_type, Literal) or str(rail_type) not in {"evolves_to", "tests_to"}:
            continue
        task = g.value(rail, WF["from"])
        target = g.value(rail, WF.to)
        if not isinstance(task, URIRef) or not isinstance(target, URIRef):
            continue
        target_is_artifact = (target, RDF.type, WF.Artifact) in g
        for owner in g.subjects(WF.has, task):
            if not isinstance(owner, URIRef):
                continue
            if target_is_artifact:
                if target in _owner_produced_artifacts(owner):
                    issues.append(
                        f"oracle artifact self-produce: {_local(task)} 의 {rail_type} 대상 artifact "
                        f"{_local(target)} 을(를) oracle workflow {_local(owner)} 가 직접 생산함 — "
                        "자기 증거 조작 루프 금지 (D-12①)"
                    )
                if not _artifact_consumed_anywhere(target):
                    warnings.append(
                        f"oracle artifact no-consumer: {_local(task)} 의 {rail_type} 대상 artifact "
                        f"{_local(target)} 을(를) 소비하는 Task/Executor 없음 — "
                        "소비 공급망이 개선의 정당화 근거 (D-12②)"
                    )
            elif _sub_workflow_connected(g, owner, target):
                issues.append(
                    f"oracle disjoint: {_local(task)} 의 {rail_type} 대상 {_local(target)} 이(가) "
                    f"소속 workflow {_local(owner)} 와 has_subWorkflow* 로 연결됨 — oracle과 대상은 disjoint"
                )
    return issues, warnings


def find_task_sharing_v07(g: Graph) -> list[str]:
    """서로 다른 Workflow가 같은 Execution을 공유하면 위반 (D-10②, partition)."""
    issues: list[str] = []
    for task in sorted(g.subjects(RDF.type, WF.Execution), key=str):
        owners = sorted(
            {o for o in g.subjects(WF.has, task) if isinstance(o, URIRef)}, key=str
        )
        if len(owners) > 1:
            names = ", ".join(_local(o) for o in owners)
            issues.append(f"execution partition: {_local(task)} 이(가) 복수 workflow에 속함 — {names}")
    return issues


PROVENANCE_PROPS = (WF.author, WF.version, WF.timestamp, WF.validation, WF.coverage, WF.confidence)


def find_provenance_coverage_v07(g: Graph) -> list[str]:
    """§6/§7 provenance 커버리지 경고 (D-22 — 오류 아님).

    - Artifact: provenance property가 하나도 없으면 경고
    - Execution: method 미선언 경고 (hasSubject는 기본값 self가 있으므로 제외)
    """
    warnings: list[str] = []
    for artifact in sorted(g.subjects(RDF.type, WF.Artifact), key=str):
        if not any(isinstance(g.value(artifact, prop), Literal) for prop in PROVENANCE_PROPS):
            warnings.append(
                f"provenance coverage: artifact {_local(artifact)} 에 provenance 없음 "
                "(author/version/timestamp/validation/coverage/confidence 중 최소 1개 권장, §6)"
            )
    for execution in sorted(g.subjects(RDF.type, WF.Execution), key=str):
        if not isinstance(g.value(execution, WF.method), Literal):
            warnings.append(
                f"execution metadata: {_local(execution)} 에 method 미선언 "
                "(prompt|script|workflow|api|manual, §7)"
            )
    return warnings


def find_uncontrolled_loops_v07(g: Graph) -> list[str]:
    """default Rail 순환 중 제어점(EvalTask / user·criteria DecisionTask) 없는 loop."""
    adjacency: dict[URIRef, list[URIRef]] = {}
    for rail in g.subjects(RDF.type, WF.Rail):
        if g.value(rail, WF.railType) != Literal("default"):
            continue
        source = g.value(rail, WF["from"])
        target = g.value(rail, WF.to)
        if isinstance(source, URIRef) and isinstance(target, URIRef):
            adjacency.setdefault(source, []).append(target)

    def is_control_point(node: URIRef) -> bool:
        if (node, RDF.type, WF.Eval) in g:
            return True
        if (node, RDF.type, WF.Decision) in g:
            if execution_subject(g, node) == "human":
                return True
            if isinstance(g.value(node, WF.criteria), Literal):
                return True
            for rail in g.objects(node, WF.hasBranch):
                if isinstance(g.value(rail, WF.criteria), Literal):
                    return True
        return False

    issues: list[str] = []
    reported: set[frozenset] = set()
    for origin in adjacency:
        stack = [(origin, [origin])]
        while stack:
            current, path = stack.pop()
            for nxt in adjacency.get(current, []):
                if nxt == origin:
                    cycle = frozenset(path)
                    if cycle in reported:
                        continue
                    reported.add(cycle)
                    if not any(is_control_point(n) for n in path):
                        names = " → ".join(_local(n) for n in path + [origin])
                        issues.append(f"uncontrolled loop (v07): {names}")
                elif nxt not in path:
                    stack.append((nxt, path + [nxt]))
    return issues


# ═══════════════════════════════ 공통 ═══════════════════════════════


def _local(node: URIRef) -> str:
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def find_legacy_yaml_residue(paths: list[Path]) -> list[str]:
    """abox 와 같은 디렉토리의 legacy workflow YAML 잔존 판정 (warning)."""
    warnings: list[str] = []
    dirs = sorted({p.parent for p in paths})
    for d in dirs:
        for y in sorted(list(d.glob("*.yaml")) + list(d.glob("*.yml"))):
            sibling = y.with_suffix("").name
            has_abox = any(
                t.name.startswith(sibling) for t in d.glob("*.abox.ttl")
            ) or (d / f"{sibling}.abox.ttl").exists()
            if has_abox:
                warnings.append(f"legacy yaml residue: {y} — sibling abox 존재, 제거 후보")
            else:
                warnings.append(f"legacy yaml residue: {y} — sibling abox 없음, migration blocker")
    return warnings


def validate_abox(targets: list[Path]) -> dict:
    paths = collect_abox_paths(targets)
    if not paths:
        return {"ok": False, "error": "no .abox.ttl found", "files": []}

    v06_paths: list[Path] = []
    v07_paths: list[Path] = []
    for path in paths:
        single = Graph()
        single.parse(str(path), format="turtle")
        (v07_paths if is_v07_graph(single) else v06_paths).append(path)

    result: dict = {
        "files": [str(p) for p in paths],
        "v06_files": [str(p) for p in v06_paths],
        "v07_files": [str(p) for p in v07_paths],
        "legacy_yaml_warnings": find_legacy_yaml_residue(paths),
    }

    # ── v0.6 스택 (기존 top-level 키 유지 — 호환) ─────────────────────────
    if v06_paths:
        g = parse_graph(v06_paths)
        uncontrolled_loops = find_uncontrolled_loops(g)
        eval_artifact_mismatches = find_eval_target_artifact_mismatches(g)
        directory_issues = find_directory_shape_issues(g)
        conforms, shacl_text = run_shacl(g)
        step_warnings = find_step_multi_outgoing(g)
        v06_ok = (
            conforms
            and not uncontrolled_loops
            and not eval_artifact_mismatches
            and not directory_issues
        )
        result.update({
            "triples": len(g),
            "uncontrolled_loops": uncontrolled_loops,
            "eval_target_artifact_mismatches": eval_artifact_mismatches,
            "directory_issues": directory_issues,
            "shacl_conforms": conforms,
            "shacl_report": shacl_text if not conforms else "",
            "step_multi_outgoing_warnings": step_warnings,
        })
    else:
        v06_ok = True
        result.update({
            "triples": 0,
            "uncontrolled_loops": [],
            "eval_target_artifact_mismatches": [],
            "directory_issues": [],
            "shacl_conforms": True,
            "shacl_report": "",
            "step_multi_outgoing_warnings": [],
        })

    # ── v0.7 스택 ────────────────────────────────────────────────────────
    if v07_paths:
        g7 = parse_graph(v07_paths)
        conforms7, shacl_text7 = run_shacl_v07(g7)
        oracle_issues, oracle_warnings = find_oracle_disjoint_violations_v07(g7)
        partition_issues = find_task_sharing_v07(g7)
        loop_issues = find_uncontrolled_loops_v07(g7)
        provenance_warnings = find_provenance_coverage_v07(g7)
        v07_ok = conforms7 and not oracle_issues and not partition_issues and not loop_issues
        result["v07"] = {
            "ok": v07_ok,
            "triples": len(g7),
            "shacl_conforms": conforms7,
            "shacl_report": shacl_text7 if not conforms7 else "",
            "oracle_disjoint_issues": oracle_issues,
            "oracle_artifact_warnings": oracle_warnings,
            "provenance_warnings": provenance_warnings,
            "task_partition_issues": partition_issues,
            "uncontrolled_loops": loop_issues,
        }
    else:
        v07_ok = True
        result["v07"] = None

    result["ok"] = v06_ok and v07_ok
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="validate_abox",
        description="TTL ABox(SSOT) shape/feedback-loop/거버넌스 검증 (v0.6 + v0.7 자동 감지)",
    )
    ap.add_argument("targets", nargs="+", help="*.abox.ttl 파일 또는 workflow 디렉토리")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="warning 도 실패로 승격")
    args = ap.parse_args(argv)

    targets = [Path(t).resolve() for t in args.targets]
    for t in targets:
        if not t.exists():
            print(f"경로 없음: {t}", file=sys.stderr)
            return 2

    res = validate_abox(targets)
    v07_res = res.get("v07") or {}
    has_warnings = bool(
        res.get("step_multi_outgoing_warnings")
        or res.get("legacy_yaml_warnings")
        or v07_res.get("oracle_artifact_warnings")
    )
    exit_fail = (not res["ok"]) or (args.strict and has_warnings)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if exit_fail else 0

    if res.get("error"):
        print(f"✗ {res['error']}", file=sys.stderr)
        return 1
    v07 = res.get("v07")
    print(
        f"files={len(res['files'])} (v06={len(res['v06_files'])}, v07={len(res['v07_files'])})  "
        f"ok={res['ok']}"
    )
    if res["uncontrolled_loops"]:
        print("✗ [v06] uncontrolled feedback loop:")
        for c in res["uncontrolled_loops"]:
            print(f"  - {c}")
    if res["eval_target_artifact_mismatches"]:
        print("✗ [v06] Eval targetArtifact shape 위반:")
        for i in res["eval_target_artifact_mismatches"]:
            print(f"  - {i}")
    if res["directory_issues"]:
        print("✗ [v06] directory shape 위반:")
        for i in res["directory_issues"]:
            print(f"  - {i}")
    if not res["shacl_conforms"]:
        print("✗ [v06] SHACL 로컬 shape 위반:")
        print(res["shacl_report"])
    if v07:
        if not v07["shacl_conforms"]:
            print("✗ [v07] SHACL shape 위반:")
            print(v07["shacl_report"])
        for key, title in (
            ("oracle_disjoint_issues", "oracle disjoint 위반"),
            ("task_partition_issues", "task partition 위반"),
            ("uncontrolled_loops", "uncontrolled feedback loop"),
        ):
            if v07[key]:
                print(f"✗ [v07] {title}:")
                for i in v07[key]:
                    print(f"  - {i}")
    if v07 and v07.get("provenance_warnings"):
        shown = v07["provenance_warnings"][:10]
        print(f"⚠ [v07] provenance coverage (§6/§7, {len(v07['provenance_warnings'])}건):")
        for w in shown:
            print(f"  - {w}")
        if len(v07["provenance_warnings"]) > 10:
            print(f"  … 외 {len(v07['provenance_warnings']) - 10}건")
    if v07 and v07.get("oracle_artifact_warnings"):
        print("⚠ [v07] oracle artifact 대상 (D-12):")
        for w in v07["oracle_artifact_warnings"]:
            print(f"  - {w}")
    if res["step_multi_outgoing_warnings"]:
        print("⚠ [v06] step multi-outgoing (Decision 모델링 권장):")
        for w in res["step_multi_outgoing_warnings"]:
            print(f"  - {w}")
    if res["legacy_yaml_warnings"]:
        print("⚠ legacy YAML residue:")
        for w in res["legacy_yaml_warnings"]:
            print(f"  - {w}")
    if res["ok"] and not exit_fail:
        tail = " (warning 있음)" if has_warnings else ""
        print("✓ ABox shape + feedback loop control 통과" + tail)
    return 1 if exit_fail else 0


if __name__ == "__main__":
    sys.exit(main())
