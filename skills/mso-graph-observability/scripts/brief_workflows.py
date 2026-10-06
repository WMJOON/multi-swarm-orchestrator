#!/usr/bin/env python3
"""workflow brief — 그림 대신 글로 요약한다.

workflow TTL ABox(Rail/Stream)를 읽어 결정적으로 두 가지를 만든다.

  에이전트용  brief/<scope>.brief.json · .brief.md · project-brief.md
              workflow 하나를 한 장으로: 흐름, 사람 승인 지점, 되돌림 루프, 입출력 artifact, 결함.
              에이전트가 workflow 를 고치거나 실행하기 전에 먼저 읽는다.
  사람 보고용  brief/report.md
              프로젝트 전체를 쉬운 한국어로: 무엇이 있고, 어디서 사람이 결정하며, 무엇을 주의해야 하나.

TTL 에 없는 의미를 만들지 않는다. 제어 흐름 추출은 mso-workflow-design 의 `wf_v07.control_graph` 가 정본이다.
원본 TTL 은 수정하지 않는다(읽기 전용). LLM 을 쓰지 않으므로 같은 입력이면 같은 결과다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace, RDF, RDFS, URIRef

WF = Namespace("https://mso.dev/ontology/workflow#")
SUBJECT_KO = {"system": "자동(시스템)", "model": "모델", "self": "에이전트", "human": "사람", "workflow": "하위 workflow", None: "-"}
SHARED_MIN = 4  # 이 수 이상의 workflow 가 만들거나 쓰는 artifact 는 인계가 아니라 공유 저장소로 본다
KIND_KO = {"task": "작업", "decision": "판단", "eval": "평가", "event": "시작 트리거", "end": "끝"}


def _load_wf_v07():
    """sibling `skills/` 우선, 없으면 `~/.claude/skills/`. 제어 흐름 추출의 정본이라 없으면 중단한다."""
    for base in (Path(__file__).resolve().parents[2], Path.home() / ".claude" / "skills"):
        path = base / "mso-workflow-design" / "scripts" / "wf_v07.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location("wf_v07_for_brief", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["wf_v07_for_brief"] = mod
            spec.loader.exec_module(mod)
            if not hasattr(mod, "control_graph"):
                raise SystemExit(f"{path}: control_graph missing (mso-workflow-design >= 0.13.0 required)")
            return mod
    raise SystemExit("mso-workflow-design/scripts/wf_v07.py not found (required for control-flow extraction)")


def _lit(g: Graph, node, *preds) -> str:
    for pred in preds:
        value = g.value(node, pred)
        if value is not None:
            return str(value)
    return ""


def _local(uri) -> str:
    text = str(uri)
    return text.rsplit("#", 1)[-1] if "#" in text else text.rsplit("/", 1)[-1]


# ── 추출 ────────────────────────────────────────────────────────────────

def _flow_order(nodes: dict[str, dict], edges: list[dict], entries: list[str]) -> tuple[list[str], list[dict]]:
    """진입 노드에서 깊이 우선으로 순회해 (읽는 순서, 되돌림 edge)를 구한다. 되돌림 = DFS 스택의 조상으로 돌아가는 edge."""
    out_edges: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        out_edges[e["source"]].append(e)
    order: list[str] = []
    back: list[dict] = []
    state: dict[str, int] = {}  # 1=스택, 2=완료

    def visit(n: str) -> None:
        state[n] = 1
        for e in sorted(out_edges[n], key=lambda x: (x["on"] or "", x["target"])):
            t = e["target"]
            if state.get(t) == 1:
                back.append(e)
            elif t not in state:
                visit(t)
        state[n] = 2
        order.append(n)

    for entry in entries:
        if entry not in state:
            visit(entry)
    for n in sorted(nodes):  # 도달 불가 노드도 빠뜨리지 않는다
        if n not in state:
            visit(n)
    return list(reversed(order)), back


def _streams(g: Graph) -> list[dict]:
    out = []
    for edge in sorted(g.subjects(RDF.type, WF.Stream), key=str):
        src, dst = g.value(edge, WF["from"]), g.value(edge, WF.to)
        if isinstance(src, URIRef) and isinstance(dst, URIRef):
            out.append({"from": src, "to": dst, "type": _lit(g, edge, WF.streamType)})
    return out


def read_workflows(files: list[Path], wf_v07) -> list[dict[str, Any]]:
    """TTL 파일들을 읽어 workflow 단위 원자료를 만든다. 한 파일에 workflow 가 여럿이면 각각 나눈다."""
    found: list[dict[str, Any]] = []
    for path in files:
        g = Graph()
        g.parse(path, format="turtle")
        cg = wf_v07.control_graph(g)
        workflows = sorted(g.subjects(WF.workflowType, None), key=str)
        if not workflows:
            continue
        by_uri = {n["uri"]: n for n in cg["nodes"]}
        for wf in workflows:
            members = {str(m) for m in g.objects(wf, WF.has)}
            nodes = {n["id"]: n for n in cg["nodes"] if n["uri"] in members}
            ids = set(nodes)
            edges = [e for e in cg["edges"] if e["source"] in ids and e["target"] in ids]
            entries = [n for n in cg["entrypoints"] if n in ids]
            stem = path.name.replace(".abox.ttl", "").replace(".ttl", "")
            scope = stem if len(workflows) == 1 else f"{stem}.{_local(wf)}"
            node_uris = {n["uri"] for n in nodes.values()}
            streams = [s for s in _streams(g) if str(s["from"]) in node_uris or str(s["to"]) in node_uris]
            labels = {str(s[k]): _lit(g, s[k], WF.label, RDFS.label) or _local(s[k]) for s in streams for k in ("from", "to")}
            found.append({
                "scope": scope, "file": str(path), "label": _lit(g, wf, WF.label, RDFS.label) or scope,
                "description": _lit(g, wf, WF.description), "type": _lit(g, wf, WF.workflowType),
                "nodes": nodes, "edges": edges, "entries": entries, "streams": streams, "labels": labels,
                "node_uris": node_uris, "errors": [e for e in cg["errors"]], "warnings": [w for w in cg["warnings"]],
                "ignored": cg["ignored"],
            })
    return found


def build_briefs(workflows: list[dict[str, Any]]) -> dict[str, Any]:
    """{"workflows": {scope: brief}, "shared": [공유 저장소]} 를 돌려준다."""
    # 프로젝트 전체의 artifact 생산·소비 (workflow 경계를 넘는 연결을 보려면 전체가 필요하다)
    producers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    consumers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    names: dict[str, str] = {}
    for w in workflows:
        names.update(w["labels"])
        for s in w["streams"]:
            if s["type"] == "produces_to" and str(s["from"]) in w["node_uris"]:
                producers[str(s["to"])].append((w["scope"], _local(s["from"])))
            elif s["type"] == "consumed_by" and str(s["to"]) in w["node_uris"]:
                consumers[str(s["from"])].append((w["scope"], _local(s["to"])))
    art_name = lambda a: names.get(a) or _local(a)
    touch: dict[str, set[str]] = defaultdict(set)
    for a, items in list(producers.items()) + list(consumers.items()):
        touch[a].update(scope for scope, _ in items)
    shared_ids = {a for a, scopes in touch.items() if len(scopes) >= SHARED_MIN}

    briefs: dict[str, Any] = {}
    for w in workflows:
        nodes, edges = w["nodes"], w["edges"]
        order, back = _flow_order(nodes, edges, w["entries"])
        lab = lambda i: nodes[i]["label"] if i in nodes else i
        out_edges: dict[str, list[dict]] = defaultdict(list)
        for e in edges:
            out_edges[e["source"]].append(e)

        human = [{"id": i, "label": nodes[i]["label"], "kind": nodes[i]["kind"], "criteria": nodes[i]["criteria"], "instruction": nodes[i]["instruction"],
                  "outcomes": [{"on": e["on"] or "다음", "to": lab(e["target"])} for e in out_edges[i]]}
                 for i in order if nodes[i]["subject"] == "human"]
        decisions = [{"id": i, "label": nodes[i]["label"], "subject": nodes[i]["subject"], "criteria": nodes[i]["criteria"],
                      "branches": [{"on": e["on"], "to": lab(e["target"])} for e in out_edges[i]]}
                     for i in order if nodes[i]["kind"] == "decision"]
        loops = [{"from": lab(e["source"]), "to": lab(e["target"]), "on": e["on"]} for e in back]

        mine = lambda a: [x for x in (producers.get(a, []), consumers.get(a, []))]
        inputs, outputs = [], []
        for s in w["streams"]:
            if s["type"] == "consumed_by" and str(s["to"]) in w["node_uris"]:
                inputs.append(str(s["from"]))
            if s["type"] == "produces_to" and str(s["from"]) in w["node_uris"]:
                outputs.append(str(s["to"]))
        inputs, outputs = sorted(set(inputs)), sorted(set(outputs))
        external = [a for a in inputs if not producers.get(a)]
        from_others = [{"artifact": art_name(a), "from": sorted({p[0] for p in producers[a] if p[0] != w["scope"]})}
                       for a in inputs if a not in shared_ids and any(p[0] != w["scope"] for p in producers.get(a, []))]
        to_others = [{"artifact": art_name(a), "to": sorted({c[0] for c in consumers[a] if c[0] != w["scope"]})}
                     for a in outputs if a not in shared_ids and any(c[0] != w["scope"] for c in consumers.get(a, []))]
        uses_shared = [art_name(a) for a in sorted(set(inputs) | set(outputs)) if a in shared_ids]
        unconsumed = [a for a in outputs if not consumers.get(a)]

        by_subject = Counter(n["subject"] for n in nodes.values() if n["kind"] != "end")
        by_kind = Counter(n["kind"] for n in nodes.values())
        steps = [i for i in order if nodes[i]["kind"] != "end"]
        defects = {
            "errors": w["errors"], "warnings": w["warnings"],
            "no_instruction": [nodes[i]["label"] for i in steps if nodes[i]["kind"] in {"task", "eval"} and not nodes[i]["instruction"]],
            "decision_without_criteria": [d["label"] for d in decisions if not d["criteria"]],
        }
        parts = [f"{len(steps)}단계"]
        if by_subject.get("human"):
            parts.append(f"사람 승인 {by_subject['human']}곳")
        else:
            parts.append("사람 승인 없음")
        if loops:
            parts.append(f"되돌림 {len(loops)}개")
        parts.append(f"입력 {len(inputs)}·산출 {len(outputs)} artifact")
        briefs[w["scope"]] = {
            "workflow": {"scope": w["scope"], "label": w["label"], "type": w["type"], "description": w["description"], "file": w["file"]},
            "summary": ", ".join(parts),
            "counts": {"steps": len(steps), "by_kind": dict(by_kind), "by_subject": {str(k): v for k, v in by_subject.items()}},
            "entry": [lab(i) for i in w["entries"]],
            "flow": [{"id": i, "label": nodes[i]["label"], "kind": nodes[i]["kind"], "subject": nodes[i]["subject"], "method": nodes[i]["method"]} for i in order],
            "human_gates": human, "decisions": decisions, "loops": loops,
            "artifacts": {"inputs": [art_name(a) for a in inputs], "outputs": [art_name(a) for a in outputs],
                          "external_inputs": [art_name(a) for a in external], "unconsumed_outputs": [art_name(a) for a in unconsumed],
                          "from_other_workflows": from_others, "to_other_workflows": to_others, "shared_stores": uses_shared},
            "defects": defects,
        }
    shared = [{"artifact": art_name(a), "producers": sorted({p[0] for p in producers.get(a, [])}), "consumers": sorted({c[0] for c in consumers.get(a, [])})}
              for a in sorted(shared_ids, key=art_name)]
    return {"workflows": briefs, "shared": shared}


# ── 렌더 ────────────────────────────────────────────────────────────────

def _defect_count(b: dict[str, Any]) -> int:
    d = b["defects"]
    return len(d["errors"]) + len(d["warnings"]) + len(d["no_instruction"]) + len(d["decision_without_criteria"])


def render_agent_brief(b: dict[str, Any]) -> str:
    w = b["workflow"]
    lines = [f"# {w['label']} (`{w['scope']}`)", "", f"> {b['summary']}", ""]
    if w["description"]:
        lines += [w["description"], ""]
    lines += [f"- 원본: `{w['file']}`  ·  type: {w['type'] or '-'}  ·  시작: {', '.join(b['entry']) or '(진입 없음)'}", "", "## 흐름", ""]
    for number, n in enumerate(b["flow"], 1):
        lines.append(f"{number}. **{n['label']}** — {KIND_KO.get(n['kind'], n['kind'])}, 주체 {SUBJECT_KO.get(n['subject'], n['subject'])}" + (f", 방식 {n['method']}" if n["method"] else ""))
    if b["decisions"]:
        lines += ["", "## 판단", ""]
        for d in b["decisions"]:
            lines.append(f"- **{d['label']}** ({SUBJECT_KO.get(d['subject'], d['subject'])}): {'; '.join(d['criteria']) or '기준 없음'}  → " + ", ".join(f"{x['on'] or '?'}→{x['to']}" for x in d["branches"]))
    if b["human_gates"]:
        lines += ["", "## 사람 승인 지점", ""]
        for h in b["human_gates"]:
            lines.append(f"- **{h['label']}**: {h['instruction'] or '; '.join(h['criteria']) or '-'}  → " + ", ".join(f"{o['on']}→{o['to']}" for o in h["outcomes"]))
    if b["loops"]:
        lines += ["", "## 되돌림 루프", ""] + [f"- {x['from']} → {x['to']}" + (f" ({x['on']})" if x["on"] else "") for x in b["loops"]]
    a = b["artifacts"]
    lines += ["", "## artifact", "", f"- 입력: {', '.join(a['inputs']) or '-'}", f"- 산출: {', '.join(a['outputs']) or '-'}"]
    if a["external_inputs"]:
        lines.append(f"- 어떤 workflow 도 만들지 않는 입력(외부): {', '.join(a['external_inputs'])}")
    if a["unconsumed_outputs"]:
        lines.append(f"- 아무도 소비하지 않는 산출: {', '.join(a['unconsumed_outputs'])}")
    for x in a["from_other_workflows"]:
        lines.append(f"- 다른 workflow 에서 받음: {x['artifact']} ← {', '.join(x['from'])}")
    for x in a["to_other_workflows"]:
        lines.append(f"- 다른 workflow 로 넘김: {x['artifact']} → {', '.join(x['to'])}")
    d = b["defects"]
    problems = [f"오류: {m}" for m in d["errors"]] + [f"경고: {m}" for m in d["warnings"]]
    problems += [f"instruction 없음: {n}" for n in d["no_instruction"]] + [f"판단 기준 없음: {n}" for n in d["decision_without_criteria"]]
    lines += ["", "## 결함", ""] + ([f"- {p}" for p in problems] if problems else ["- 없음"])
    return "\n".join(lines) + "\n"


def render_project_brief(model: dict[str, Any]) -> str:
    briefs = model["workflows"]
    lines = ["# workflow 목록 (에이전트용)", "", "| scope | 이름 | 요약 | 결함 |", "|---|---|---|---|"]
    for scope, b in briefs.items():
        lines.append(f"| [`{scope}`]({scope}.brief.md) | {b['workflow']['label']} | {b['summary']} | {_defect_count(b)} |")
    hand = [(s, x) for s, b in briefs.items() for x in b["artifacts"]["to_other_workflows"]]
    if hand:
        lines += ["", "## workflow 간 인계", ""] + [f"- `{s}` →({x['artifact']})→ {', '.join('`'+t+'`' for t in x['to'])}" for s, x in hand]
    if model["shared"]:
        lines += ["", f"## 공유 저장소 ({SHARED_MIN}개 이상의 workflow 가 사용)", ""]
        lines += [f"- **{x['artifact']}** — 생산 {', '.join('`'+p+'`' for p in x['producers']) or '-'} / 소비 {', '.join('`'+c+'`' for c in x['consumers']) or '-'}" for x in model["shared"]]
    return "\n".join(lines) + "\n"


def _first_sentence(text: str, limit: int = 90) -> str:
    sentence = text.split(". ")[0].split("。")[0].strip()
    return sentence if len(sentence) <= limit else sentence[:limit].rstrip() + "…"


def render_human_report(model: dict[str, Any], project: str, today: str) -> str:
    briefs = model["workflows"]
    name_of = lambda scope: briefs[scope]["workflow"]["label"] if scope in briefs else scope
    total_gates = sum(len(b["human_gates"]) for b in briefs.values())
    total_loops = sum(len(b["loops"]) for b in briefs.values())
    lines = [f"# {project} workflow 현황 ({today})", "",
             f"workflow {len(briefs)}개, 사람이 결정하는 지점 {total_gates}곳, 되돌림 루프 {total_loops}개. "
             "TTL 정의를 읽어 자동으로 정리한 글이며 정의를 바꾸지 않았습니다.", "",
             "## 한눈에 보기", "", "| 이름 | 하는 일 | 규모 | 사람이 결정하는 곳 | 주의 |", "|---|---|---|---|---|"]
    for b in briefs.values():
        w = b["workflow"]
        gates = ", ".join(h["label"] for h in b["human_gates"]) or "없음"
        lines.append(f"| {w['label']} | {_first_sentence(w['description']) or '-'} | {b['counts']['steps']}단계 | {gates} | {_defect_count(b) or '-'} |")

    lines += ["", "## 사람이 결정해야 하는 곳", ""]
    any_gate = False
    for b in briefs.values():
        for h in b["human_gates"]:
            any_gate = True
            choices = ", ".join(o["on"] for o in h["outcomes"])
            lines.append(f"- **{b['workflow']['label']} · {h['label']}** — {h['instruction'] or '; '.join(h['criteria']) or '(판단 기준 미기재)'}" + (f" (선택: {choices})" if choices and choices != "다음" else ""))
    if not any_gate:
        lines.append("- 사람 승인이 정의된 곳이 없습니다. 자동으로 끝까지 진행되는 workflow 뿐입니다.")

    hand = [(b["workflow"]["label"], x) for b in briefs.values() for x in b["artifacts"]["to_other_workflows"]]
    lines += ["", "## workflow끼리 이어지는 곳", ""]
    lines += [f"- **{src}** 이(가) 만든 *{x['artifact']}* 을(를) {', '.join(name_of(t) for t in x['to'])} 이(가) 이어서 씁니다." for src, x in hand] or ["- 특정 workflow가 다른 workflow에 직접 넘기는 산출물은 정의돼 있지 않습니다."]
    if model["shared"]:
        lines += ["", f"## 여러 workflow가 함께 쓰는 자료 ({SHARED_MIN}개 이상)", "",
                  "아래 자료는 한 workflow가 다른 workflow에 넘기는 것이 아니라 모두가 읽고 쓰는 공용 저장소입니다. 바뀌면 여러 workflow에 영향이 갑니다.", ""]
        lines += [f"- **{x['artifact']}** — 만드는 곳 {len(x['producers'])}, 쓰는 곳 {len(x['consumers'])}: {', '.join(name_of(c) for c in x['consumers'])}" for x in model["shared"]]

    notes: list[str] = []
    for b in briefs.values():
        name, a, d = b["workflow"]["label"], b["artifacts"], b["defects"]
        model_steps = b["counts"]["by_subject"].get("model", 0)
        if not b["human_gates"] and model_steps >= 2:
            notes.append(f"**{name}**: 모델이 판단하는 단계가 {model_steps}개인데 사람 승인 지점이 없습니다.")
        blind = [h["label"] for h in b["human_gates"] if not (h["instruction"] or h["criteria"])]
        if blind:
            notes.append(f"**{name}**: 사람이 결정하는 곳에 판단 기준이 적혀 있지 않습니다 — {', '.join(blind)}. 무엇을 보고 결정할지 정의해 두면 좋습니다.")
        if a["unconsumed_outputs"]:
            notes.append(f"**{name}**: 만들고도 아무도 쓰지 않는 산출물이 있습니다 — {', '.join(a['unconsumed_outputs'][:4])}")
        if a["external_inputs"]:
            notes.append(f"**{name}**: 어느 workflow 도 만들지 않는 입력(외부에서 와야 함) — {', '.join(a['external_inputs'][:4])}")
        for m in d["errors"]:
            notes.append(f"**{name}**: 정의 오류 — {m}")
        for m in d["warnings"]:
            notes.append(f"**{name}**: 정의 경고 — {m}")
        if d["no_instruction"]:
            notes.append(f"**{name}**: 무엇을 하는지 적히지 않은 단계 — {', '.join(d['no_instruction'][:4])}")
        human_labels = {h["label"] for h in b["human_gates"]}
        other = [x for x in d["decision_without_criteria"] if x not in human_labels]
        if other:
            notes.append(f"**{name}**: 판단 기준이 없는 판단 — {', '.join(other[:4])}")
    lines += ["", "## 주의할 점", ""] + ([f"- {n}" for n in notes] if notes else ["- 정의상 눈에 띄는 문제는 없습니다."])

    lines += ["", "## 각 workflow", ""]
    for b in briefs.values():
        w, a = b["workflow"], b["artifacts"]
        path = " → ".join(n["label"] for n in b["flow"] if n["kind"] != "end")
        lines += [f"### {w['label']}", "", w["description"] or "(설명이 적혀 있지 않습니다)", "", f"- 흐름: {path}"]
        lines.append("- 되돌아가는 경우: " + ("; ".join(f"{x['from']}에서 {x['to']}(으)로" + (f" ({x['on']})" if x["on"] else "") for x in b["loops"]) if b["loops"] else "없음"))
        lines.append(f"- 받는 것: {', '.join(a['inputs']) or '-'}")
        lines += [f"- 남기는 것: {', '.join(a['outputs']) or '-'}", ""]
    return "\n".join(lines).rstrip() + "\n"


# ── CLI ─────────────────────────────────────────────────────────────────

def run(root: Path, out: Path | None = None, workflow_dir: Path | None = None, project: str | None = None, today: str | None = None) -> dict[str, Any]:
    import datetime as dt
    wf_dir = workflow_dir or root / "agent-context" / "workflow"
    files = sorted(p for p in wf_dir.rglob("*.abox.ttl")) if wf_dir.is_dir() else []
    model = build_briefs(read_workflows(files, _load_wf_v07()))
    briefs = model["workflows"]
    out = out or root / "agent-context" / "observability" / "brief"
    out.mkdir(parents=True, exist_ok=True)
    for scope, b in briefs.items():
        (out / f"{scope}.brief.json").write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / f"{scope}.brief.md").write_text(render_agent_brief(b), encoding="utf-8")
    (out / "project-brief.md").write_text(render_project_brief(model), encoding="utf-8")
    (out / "report.md").write_text(render_human_report(model, project or root.resolve().name, today or dt.date.today().isoformat()), encoding="utf-8")
    return {"out": str(out), "workflows": list(briefs), "files": len(files)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write workflow briefs (agent) and a plain-language report (human) from workflow TTL ABox.")
    ap.add_argument("--root", type=Path, default=Path("."), help="project root")
    ap.add_argument("--workflow-dir", type=Path, help="default: <root>/agent-context/workflow")
    ap.add_argument("--out", type=Path, help="default: <root>/agent-context/observability/brief")
    ap.add_argument("--project", help="project name for the report title (default: root directory name)")
    args = ap.parse_args(argv)
    result = run(args.root, args.out, args.workflow_dir, args.project)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["workflows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
