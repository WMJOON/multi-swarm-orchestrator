#!/usr/bin/env python3
"""migrate_abox_v06_to_v07 — v0.6 workflow ABox를 v0.7 Rail/Stream 정본으로 변환.

SPEC: planning/mso-v0.7.0-SPEC-rail-stream-ontology.md §6 (B-1)

변환 규칙 (r2, D-13~D-16):
  wf:Step                          → wf:Task (+Execution +Node)
  wf:Decision (decisionSubject)    → wf:Decision (+Execution) — hasSubject(user→human, agent→self)
  wf:Eval (oracleType)             → wf:Eval (+Execution) — hasSubject(metric→system)
  wf:target (Eval→Workflow)        → Rail(measures) — WorkflowGraph 측정 단위 (D-16)
  wf:next                          → Rail(default)
  Branch(on/gotoNode)              → Rail(default, wf:on) + hasBranch, Branch 노드 제거
  wf:measures / wf:targetArtifact  → Artifact 노드 + Rail(measured_by)
  wf:evolves                       → Rail(evolves_to)
  wf:exercises                     → workflowType=oracle 승격 + 경고 (tests_to로 완전 흡수, Q-1)
  wf:usesTool "[[x]]"              → 위임 Execution(hasSubject=system) + Rail(delegates_to) (D-15)
  wf:directory bnode               → Artifact 노드 + Stream(consumed_by/produces_to)
                                     (위임 task의 입력은 Rail(reads), §3.3 한쌍 규칙)
  wf:deliverables                  → Artifact 노드 + Stream(produces_to)
  wf:hasNode                       → wf:has (+ Start/End 합성, workflowType 판정)

Usage:
  python migrate_abox_v06_to_v07.py <dir|file.abox.ttl> [--replace] [--check]

기본은 sibling `<name>.v07.abox.ttl` 생성. --replace 는 원본 덮어쓰기.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_v07 import WF, V06_SUBJECT_MAP  # noqa: E402

TOOL_RE = re.compile(r"^\[\[(.+)\]\]$")

# v0.6 소비/생산 dirRole 해석 (observe data_edge_labels와 동일 의미)
INTERNAL_ROLES = {"implementation", "tool_internal", "internal"}


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFC", text.strip())
    text = re.sub(r"[^\w.\-#]+", "_", text)
    return text.strip("_") or "x"


def _role_consumes(role: str) -> bool:
    role_norm = role.lower().replace("-", "_")
    return role_norm in {"input", "input_output", "reference", "instruction"} or "input" in role_norm


def _role_produces(role: str) -> bool:
    role_norm = role.lower().replace("-", "_")
    return "output" in role_norm or role_norm in {"staging", "generated", "write"}


class Migrator:
    def __init__(self, src: Graph):
        self.src = src
        self.out = Graph()
        self.out.bind("wf", WF)
        self.warnings: list[str] = []
        self._artifact_by_locator: dict[tuple[str, str], URIRef] = {}
        self._converted_predicates = {
            WF.next, WF.hasBranch, WF.on, WF.goto, WF.gotoNode,
            WF.measures, WF.evolves, WF.exercises, WF.usesTool,
            WF.directory, WF.dirPath, WF.dirRole, WF.dirNote,
            WF.deliverables, WF.decisionSubject, WF.oracleType,
            WF.hasNode, WF.target,
        }
        self._converted_types = {WF.Step, WF.Decision, WF.Eval, WF.Branch, WF.Task}
        self._branch_nodes = set(self.src.objects(None, WF.hasBranch))
        self._directory_nodes = set(self.src.objects(None, WF.directory))

    # ── 공통 헬퍼 ────────────────────────────────────────────────────────

    def _scope_of_workflow(self, workflow: URIRef) -> str:
        text = str(workflow)
        marker = "workflow/"
        idx = text.find(marker)
        return _slug(text[idx + len(marker):]) if idx >= 0 else _slug(text.rsplit("/", 1)[-1])

    def _rail(self, scope: str, source: URIRef, target: URIRef, rail_type: str,
              on: str | None = None, criteria: str | None = None) -> URIRef:
        suffix = f"__{_slug(on)}" if on else ""
        uri = WF[f"rail/{scope}/{_slug(_local(source))}__{rail_type}__{_slug(_local(target))}{suffix}"]
        self.out.add((uri, RDF.type, WF.Rail))
        self.out.add((uri, RDF.type, WF.Edge))
        self.out.add((uri, WF["from"], source))
        self.out.add((uri, WF.to, target))
        self.out.add((uri, WF.railType, Literal(rail_type)))
        if on:
            self.out.add((uri, WF.on, Literal(on)))
        if criteria:
            self.out.add((uri, WF.criteria, Literal(criteria)))
        return uri

    def _stream(self, scope: str, source: URIRef, target: URIRef, stream_type: str) -> URIRef:
        uri = WF[f"stream/{scope}/{_slug(_local(source))}__{stream_type}__{_slug(_local(target))}"]
        self.out.add((uri, RDF.type, WF.Stream))
        self.out.add((uri, RDF.type, WF.Edge))
        self.out.add((uri, WF["from"], source))
        self.out.add((uri, WF.to, target))
        self.out.add((uri, WF.streamType, Literal(stream_type)))
        return uri

    def _artifact(self, scope: str, locator: str, artifact_type: str | None = None) -> URIRef:
        key = (scope, locator)
        if key in self._artifact_by_locator:
            return self._artifact_by_locator[key]
        uri = WF[f"artifact/{scope}/{_slug(locator)}"]
        self.out.add((uri, RDF.type, WF.Artifact))
        self.out.add((uri, RDF.type, WF.Node))
        self.out.add((uri, WF.locator, Literal(locator)))
        self.out.add((uri, RDFS.label, Literal(locator)))
        if artifact_type:
            self.out.add((uri, WF.artifactType, Literal(artifact_type)))
        self._artifact_by_locator[key] = uri
        return uri

    def _delegated_execution(self, scope: str, delegator: URIRef, name: str) -> URIRef:
        """usesTool → 위임 Execution (D-15). plain Execution — Task가 아니므로
        single-out 제약을 받지 않는다. hasSubject=system, subjectDetail=원문."""
        uri = WF[f"node/{scope}/{_slug(_local(delegator))}__exec_{_slug(name)}"]
        self.out.add((uri, RDF.type, WF.Execution))
        self.out.add((uri, RDF.type, WF.Node))
        self.out.add((uri, RDFS.label, Literal(name)))
        self.out.add((uri, WF.hasSubject, Literal("system")))
        self.out.add((uri, WF.subjectDetail, Literal(f"[[{name}]]")))
        return uri

    def _has_delegation(self, node: URIRef) -> bool:
        return next(self.src.objects(node, WF.usesTool), None) is not None

    # ── 변환 단계 ────────────────────────────────────────────────────────

    def migrate(self) -> Graph:
        self._pass_through()
        self._convert_nodes()
        self._goto_index = self._node_index()
        workflows = self._workflow_members()
        for workflow, members in workflows.items():
            scope = self._scope_of_workflow(workflow)
            end_uri = WF[f"node/{scope}/end"]
            self._convert_control_edges(workflow, scope, members, end_uri)
            self._convert_node_payloads(scope, members)
            self._synthesize_terminals(workflow, scope, members, end_uri)
            self._assign_workflow_type(workflow, members)
        self._convert_oracle_edges(workflows)
        return self.out

    def _pass_through(self):
        """변환 대상이 아닌 triple을 그대로 복사."""
        for s, p, o in self.src:
            if p in self._converted_predicates:
                continue
            if p == RDF.type and o in self._converted_types:
                continue
            if s in self._branch_nodes or s in self._directory_nodes:
                continue
            self.out.add((s, p, o))

    def _convert_nodes(self):
        for node in set(self.src.subjects(RDF.type, WF.Step)):
            if (node, RDF.type, WF.Decision) in self.src or (node, RDF.type, WF.Eval) in self.src:
                continue
            self.out.add((node, RDF.type, WF.Task))
            self.out.add((node, RDF.type, WF.Execution))
            self.out.add((node, RDF.type, WF.Node))
        for node in set(self.src.subjects(RDF.type, WF.Decision)):
            self.out.add((node, RDF.type, WF.Decision))
            self.out.add((node, RDF.type, WF.Execution))
            self.out.add((node, RDF.type, WF.Node))
            subject = self._map_subject(self.src.value(node, WF.decisionSubject)) or self._judge_subject(node)
            if subject and subject != "self":
                self.out.add((node, WF.hasSubject, Literal(subject)))
        for node in set(self.src.subjects(RDF.type, WF.Eval)):
            self.out.add((node, RDF.type, WF.Eval))
            self.out.add((node, RDF.type, WF.Execution))
            self.out.add((node, RDF.type, WF.Node))
            subject = self._map_subject(self.src.value(node, WF.oracleType)) or self._judge_subject(node)
            if subject and subject != "self":
                self.out.add((node, WF.hasSubject, Literal(subject)))

    @staticmethod
    def _map_subject(value) -> str | None:
        """v0.6 subject(user/agent/metric) → r2 hasSubject (Q-6: user→human, agent→self, metric→system)."""
        if not isinstance(value, Literal):
            return None
        return V06_SUBJECT_MAP.get(str(value).strip().lower())

    def _judge_subject(self, node: URIRef) -> str | None:
        """legacy wf:judge → hasSubject 매핑 (HITL/HITLFE→human, HOTL/HOOTL→self, METRIC→system)."""
        judge_value = self.src.value(node, WF.judge)
        if not isinstance(judge_value, Literal):
            return None
        judge = str(judge_value).strip().upper()
        if judge in {"HITL", "HITLFE"}:
            return "human"
        if judge in {"HOTL", "HOOTL"}:
            return "self"
        if judge == "METRIC":
            return "system"
        return None

    def _workflow_members(self) -> dict[URIRef, list[URIRef]]:
        """hasNode 컨테이너 수집. legacy wf:Phase 도 Workflow 로 취급한다 (v0.6.1 이전 호환)."""
        workflows: dict[URIRef, list[URIRef]] = {}
        containers = set(self.src.subjects(RDF.type, WF.Workflow)) | set(
            self.src.subjects(RDF.type, WF.Phase)
        )
        for workflow in containers:
            members = [n for n in self.src.objects(workflow, WF.hasNode) if isinstance(n, URIRef)]
            if members:
                workflows[workflow] = sorted(members, key=str)
                if (workflow, RDF.type, WF.Workflow) not in self.src:
                    self.out.add((workflow, RDF.type, WF.Workflow))
                    self.warnings.append(
                        f"{self._scope_of_workflow(workflow)}: legacy wf:Phase 컨테이너 — wf:Workflow로 승격"
                    )
        return workflows

    def _node_index(self) -> dict[str, URIRef]:
        """goto 문자열 해석용 — 그래프 전역 실행 노드의 local id 인덱스 (cross-phase goto 지원)."""
        index: dict[str, URIRef] = {}
        for cls in (WF.Step, WF.Decision, WF.Eval, WF.Event, WF.Group):
            for node in self.src.subjects(RDF.type, cls):
                if isinstance(node, URIRef):
                    index.setdefault(_local(node), node)
        return index

    def _convert_control_edges(self, workflow, scope, members, end_uri):
        member_set = set(members)
        for node in members:
            self.out.add((workflow, WF.has, node))
            # wf:next → Rail(default).
            # 단, 다른 workflow(oracle)의 Eval로 향하는 next는 제거한다 —
            # v0.7에서 Eval 진입은 control rail이 아니라 measured_by rail이다.
            for target in self.src.objects(node, WF.next):
                if not isinstance(target, URIRef):
                    continue
                if target not in member_set and (target, RDF.type, WF.Eval) in self.src:
                    self.warnings.append(
                        f"{scope}: {_local(node)} --next--> {_local(target)} (cross-workflow Eval) 제거 — "
                        "v0.7 Eval 진입은 measured_by rail"
                    )
                    continue
                self._rail(scope, node, target, "default")
            # Branch → Rail(default, on) + hasBranch.
            # gotoNode(URI)가 없으면 goto 문자열을 member local id로 해석한다
            # (flat-URI legacy ABox 지원). 둘 다 없으면 End로 (v0.6 pass 패턴).
            for branch in self.src.objects(node, WF.hasBranch):
                on_value = self.src.value(branch, WF.on)
                on = str(on_value) if isinstance(on_value, Literal) else None
                criteria_value = self.src.value(branch, WF.criteria)
                criteria = str(criteria_value) if isinstance(criteria_value, Literal) else None
                goto_node = self.src.value(branch, WF.gotoNode)
                if isinstance(goto_node, URIRef):
                    target = goto_node
                else:
                    goto_value = self.src.value(branch, WF.goto)
                    goto_id = str(goto_value) if isinstance(goto_value, Literal) else ""
                    target = self._goto_index.get(goto_id) or end_uri
                    if goto_id and target is end_uri:
                        self.warnings.append(
                            f"{scope}: {_local(node)} branch goto '{goto_id}' 해석 실패 (dangling) — End로 연결"
                        )
                rail = self._rail(scope, node, target, "default", on=on, criteria=criteria)
                self.out.add((node, WF.hasBranch, rail))


    def _convert_node_payloads(self, scope, members):
        for node in members:
            delegated = self._has_delegation(node)
            delegate_exec = None
            for tool_value in self.src.objects(node, WF.usesTool):
                match = TOOL_RE.match(str(tool_value).strip())
                name = match.group(1) if match else str(tool_value).strip()
                delegate_exec = self._delegated_execution(scope, node, name)
                self._rail(scope, node, delegate_exec, "delegates_to")
                # 위임 Execution도 같은 workflow의 구성원 (partition)
                for owner in self.src.subjects(WF.hasNode, node):
                    self.out.add((owner, WF.has, delegate_exec))

            producer = delegate_exec if (delegated and delegate_exec is not None) else node

            for directory in self.src.objects(node, WF.directory):
                path_value = self.src.value(directory, WF.dirPath)
                if not isinstance(path_value, Literal):
                    continue
                role_value = self.src.value(directory, WF.dirRole)
                role = str(role_value) if isinstance(role_value, Literal) else "reference"
                if role.lower().replace("-", "_") in INTERNAL_ROLES:
                    continue
                at_value = self.src.value(directory, WF.artifactType)
                artifact = self._artifact(
                    scope, str(path_value),
                    str(at_value) if isinstance(at_value, Literal) else None,
                )
                if _role_consumes(role):
                    if delegated:
                        # §3.3 한쌍: 위임 task의 입력은 Workflow Graph의 reads Rail로 정본 선언
                        self._rail(scope, artifact, node, "reads")
                    else:
                        self._stream(scope, artifact, node, "consumed_by")
                if _role_produces(role):
                    self._stream(scope, producer, artifact, "produces_to")

            for deliverable in self.src.objects(node, WF.deliverables):
                if isinstance(deliverable, Literal):
                    artifact = self._artifact(scope, str(deliverable))
                    self._stream(scope, producer, artifact, "produces_to")

            # Eval: targetArtifact → measured_by(증거), target → measures(평가 단위, D-16),
            # orderArtifact → produces_to
            if (node, RDF.type, WF.Eval) in self.src:
                for ta in self.src.objects(node, WF.targetArtifact):
                    if isinstance(ta, Literal) and not TOOL_RE.match(str(ta).strip()):
                        artifact = self._artifact(scope, str(ta))
                        self._rail(scope, artifact, node, "measured_by")
                measures_emitted = False
                for target_wf in self.src.objects(node, WF.target):
                    if isinstance(target_wf, URIRef):
                        self._rail(scope, node, target_wf, "measures")
                        measures_emitted = True
                if not measures_emitted:
                    self.warnings.append(
                        f"{scope}: Eval {_local(node)} 에 wf:target 없음 — measures rail 미생성 "
                        "(D-16: 평가 단위 WorkflowGraph를 수동 선언 필요)"
                    )
                for oa in self.src.objects(node, WF.orderArtifact):
                    if isinstance(oa, Literal):
                        artifact = self._artifact(scope, str(oa))
                        self._stream(scope, node, artifact, "produces_to")

    def _synthesize_terminals(self, workflow, scope, members, end_uri):
        member_set = set(members)
        incoming: set[URIRef] = set()
        outgoing: set[URIRef] = set()
        for rail in self.out.subjects(RDF.type, WF.Rail):
            if self.out.value(rail, WF.railType) != Literal("default"):
                continue
            source = self.out.value(rail, WF["from"])
            target = self.out.value(rail, WF.to)
            if source in member_set:
                outgoing.add(source)
            if target in member_set:
                incoming.add(target)

        start_uri = WF[f"node/{scope}/start"]
        self.out.add((start_uri, RDF.type, WF.Start))
        self.out.add((start_uri, RDF.type, WF.Node))
        self.out.add((start_uri, RDFS.label, Literal(f"{scope} start")))
        self.out.add((end_uri, RDF.type, WF.End))
        self.out.add((end_uri, RDF.type, WF.Node))
        self.out.add((end_uri, RDFS.label, Literal(f"{scope} end")))
        self.out.add((workflow, WF.has, start_uri))
        self.out.add((workflow, WF.has, end_uri))

        entries = [n for n in members if n not in incoming]
        exits = [n for n in members if n not in outgoing]
        if not entries:
            self.warnings.append(f"{scope}: 진입점 없음(모든 노드에 in-rail) — Start를 첫 멤버에 연결")
            entries = members[:1]
        for node in entries:
            self._rail(scope, start_uri, node, "default")
        for node in exits:
            self._rail(scope, node, end_uri, "default")

    def _assign_workflow_type(self, workflow, members):
        has_eval = any((n, RDF.type, WF.Eval) in self.src for n in members)
        exercises = next(self.src.objects(workflow, WF.exercises), None)
        wf_type = "oracle" if (has_eval or exercises is not None) else "base"
        self.out.add((workflow, WF.workflowType, Literal(wf_type)))
        if exercises is not None:
            self.warnings.append(
                f"{self._scope_of_workflow(workflow)}: wf:exercises는 tests_to로 완전 흡수됨(Q-1) — "
                "member task에 tests_to Rail을 선언해야 함 (자동 변환 불가)"
            )

    def _convert_oracle_edges(self, workflows):
        node_scope: dict[URIRef, str] = {}
        for workflow, members in workflows.items():
            scope = self._scope_of_workflow(workflow)
            for member in members:
                node_scope[member] = scope
        for node, target in self.src.subject_objects(WF.evolves):
            if isinstance(node, URIRef) and isinstance(target, URIRef):
                scope = node_scope.get(node, "shared")
                self._rail(scope, node, target, "evolves_to")


def _local(node: URIRef) -> str:
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def migrate_file(path: Path, replace: bool = False) -> tuple[Path, list[str]]:
    src = Graph()
    src.parse(str(path), format="turtle")
    migrator = Migrator(src)
    out = migrator.migrate()
    if replace:
        target = path
    elif path.name.endswith(".abox.ttl"):
        target = path.with_name(path.name[: -len(".abox.ttl")] + ".v07.abox.ttl")
    else:
        target = path.with_suffix(".v07.ttl")
    target.write_text(out.serialize(format="turtle"), encoding="utf-8")
    return target, migrator.warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="migrate_abox_v06_to_v07",
                                 description="v0.6 workflow ABox → v0.7 Rail/Stream 정본 변환")
    ap.add_argument("targets", nargs="+", help="*.abox.ttl 파일 또는 디렉토리")
    ap.add_argument("--replace", action="store_true", help="원본 덮어쓰기 (기본: sibling .v07.abox.ttl)")
    args = ap.parse_args(argv)

    paths: list[Path] = []
    for raw in args.targets:
        target = Path(raw).resolve()
        if target.is_dir():
            paths.extend(sorted(p for p in target.rglob("*.abox.ttl")
                                if not p.name.endswith(".v07.abox.ttl")))
        elif target.exists():
            paths.append(target)
        else:
            print(f"경로 없음: {target}", file=sys.stderr)
            return 2

    if not paths:
        print("변환할 .abox.ttl 없음", file=sys.stderr)
        return 1

    status = 0
    for path in paths:
        written, warnings = migrate_file(path, replace=args.replace)
        print(f"✓ {path.name} → {written.name}")
        for warning in warnings:
            print(f"  ⚠ {warning}")
    return status


if __name__ == "__main__":
    sys.exit(main())
