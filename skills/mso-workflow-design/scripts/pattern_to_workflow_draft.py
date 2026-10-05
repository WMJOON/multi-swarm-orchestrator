#!/usr/bin/env python3
"""pattern_to_workflow_draft.py — work-memory pattern(PT)에서 workflow ABox 초안(draft)을 만든다.

패턴이 에피소드(EP) 여러 개로 일반화되어 있고(기본 2개 이상) 본문이 번호 매긴 단계("1. ... 2. ...")를
가질 때만 만든다. 결정론적 변환이며 모델을 부르지 않는다. 산출물은 항상 status "draft" 이고
`<workflow-dir>/drafts/` 에 쓴다(활성 workflow 로 관측되지 않는다). 정식 workflow 로 올리는 것은
사람의 승인 몫이며 이 스크립트는 승격하지 않는다.

변환 규칙 (프로토타입, 순차 Task 체인만):
  Start -> Task(단계1) -> Task(단계2) ... -> End.  단계 제목 = 번호 뒤 첫 ':' 앞, 지시문 = 나머지(300자).
  검증/게이트 성격 단계(검증, 게이트, round-trip, validate, 승인)는 wf:description 에 '게이트 후보'로만 적는다.
  Decision/분기 rail 은 만들지 않는다(사람이 설계).

사용법:
  pattern_to_workflow_draft.py --pattern PT-0001 [--root R] [--workmem DIR] [--workflow-dir D] [--min-episodes 2] [--dry-run]
종료 코드: 0 생성, 2 패턴 없음/단계 없음, 3 근거 에피소드 부족
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

GATE = re.compile(r"검증|게이트|round-trip|validate|승인|shapes", re.I)
STEP = re.compile(r"(?:(?<=\s)|^)(\d{1,2})\.\s+(.+?)(?=(?:\s\d{1,2}\.\s)|\Z)", re.S)
EP_REL = {"generalized-in", "shows-pattern"}


def load_pattern(workmem: Path, pid: str) -> dict | None:
    f = workmem / "insight-record" / "pattern.jsonl"
    if not f.is_file():
        return None
    for ln in f.read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        if d.get("id") == pid:
            return d
    return None


def parse_steps(text: str) -> list[tuple[str, str]]:
    body = text.split("패턴:", 1)[1] if "패턴:" in text else text
    out = []
    for _, seg in STEP.findall(body):
        seg = " ".join(seg.split())
        title, _, rest = seg.partition(":")
        if not rest:
            title, rest = seg[:40], seg
        out.append((title.strip(), rest.strip()))
    return out


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_ttl(pid: str, title: str, eps: list[str], steps: list[tuple[str, str]]) -> str:
    wid = f"Draft{pid.replace('-', '')}"
    n = len(steps)
    nodes = ["Start"] + [f"S{i+1}" for i in range(n)] + ["End"]
    L = ["@prefix wf: <https://mso.dev/ontology/workflow#> .", "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", ""]
    gates = [t for t, b in steps if GATE.search(t + " " + b)]
    desc = f"Draft derived from work-memory pattern {pid} (episodes: {', '.join(eps)}). Requires user approval before use."
    if gates:
        desc += " Gate candidates (not modeled): " + "; ".join(gates)
    L.append(f"<#{wid}> a wf:Workflow ;")
    L.append(f'  rdfs:label "{esc(title)}" ;')
    L.append(f'  rdfs:comment "{esc(desc)}" ;')
    L.append(f'  wf:description "{esc(desc)}" ;')
    L.append('  wf:status "draft" ; wf:workflowType "base" ;')
    L.append("  wf:has " + ", ".join(f"<#{x}>" for x in nodes) + " .\n")
    L.append(f'<#Start> a wf:Node, wf:Start ; wf:status "draft" ; wf:inWorkflow <#{wid}> .')
    L.append(f'<#End> a wf:Node, wf:End ; wf:status "draft" ; wf:inWorkflow <#{wid}> .')
    for i, (t, b) in enumerate(steps):
        L.append(f'<#S{i+1}> a wf:Node, wf:Execution, wf:Task ; rdfs:label "{esc(t)}" ; wf:hasSubject "model" ; wf:method "prompt" ; '
                 f'wf:instruction "{esc(b[:300])}" ; wf:status "draft" ; wf:inWorkflow <#{wid}> .')
    L.append("")
    for i in range(len(nodes) - 1):
        L.append(f'<#r{i+1}> a wf:Edge, wf:Rail ; wf:from <#{nodes[i]}> ; wf:to <#{nodes[i+1]}> ; wf:railType "default" ; wf:status "draft" ; wf:inWorkflow <#{wid}> .')
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--workmem")
    ap.add_argument("--workflow-dir", default="agent-context/workflow")
    ap.add_argument("--min-episodes", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    wm = Path(a.workmem).resolve() if a.workmem else Path(os.environ.get("WORKMEM_DIR") or root / "agent-context/work-memory").resolve()
    pt = load_pattern(wm, a.pattern)
    if pt is None:
        print(f"패턴을 찾지 못했습니다: {a.pattern} ({wm})"); return 2
    eps = [r["target"] for r in pt.get("relations", []) if r.get("type") in EP_REL]
    if len(eps) < a.min_episodes:
        print(f"근거 에피소드 {len(eps)}개 < {a.min_episodes}개: 초안을 만들지 않습니다"); return 3
    steps = parse_steps(pt.get("text", ""))
    if len(steps) < 2:
        print("번호 매긴 단계(2개 이상)를 찾지 못했습니다. 절차형 패턴이 아니면 workflow 후보가 아닙니다"); return 2
    ttl = build_ttl(a.pattern, pt.get("title", a.pattern), eps, steps)
    out = root / a.workflow_dir / "drafts" / f"workflow-{a.pattern.lower()}.abox.ttl"
    if a.dry_run:
        print(ttl); print(f"# dry-run: {out} 에 쓰지 않았습니다"); return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ttl, encoding="utf-8")
    print(f"초안 생성: {out} (단계 {len(steps)}개, 에피소드 {', '.join(eps)})\n승격은 사용자 승인 후 수동으로 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
