#!/usr/bin/env python3
"""work-memory 분석 LangGraph (mso-workflow-optimizer).

agent-context/work-memory 를 읽기 전용으로 분석해 개선 **제안 리포트**를 만든다. work-memory 에는 쓰지 않는다.

그래프:
  load ─┬─ promotion ─┐
        ├─ workflow  ─┤
        ├─ stale     ─┼─ collect ─┬─ draft(모델 요약, 선택) ─┐
        └─ quality   ─┘           └──────────────────────────┴─ publish

- 분석(promotion/workflow/stale/quality)은 `wm_analyze.py` 의 결정적 코드다. LLM 이 없어도 완결된 리포트가 나온다.
- draft 노드는 체크포인터가 있고 `--draft` 일 때만 LangGraph interrupt 로 멈춘다. control plane(Claude Code/Codex)이
  `draft_pack.json` 을 읽고 요약·제안 문안을 써서 resume 으로 돌려주면 publish 가 리포트에 합친다.
- langgraph 가 없으면 같은 노드 함수를 순서대로 실행한다(draft 는 건너뛴다).

사용:
  analyze_work_memory.py <work-memory dir> [--out DIR] [--project-root DIR] [--stale-days N] [--max-per-kind N]
  analyze_work_memory.py <wm> --draft --checkpoint run.sqlite --thread T       # draft_pack.json 을 쓰고 멈춤
  analyze_work_memory.py --resume T --checkpoint run.sqlite --draft-file narrative.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import operator
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_analyze as wa  # noqa: E402

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional runtime
    END = START = StateGraph = Command = interrupt = None
    LANGGRAPH_AVAILABLE = False

_CHECKPOINTED = False
DRAFT_EXPECTS = {
    "summary": "전체 요약(한국어). 가장 먼저 다룰 제안 3개와 이유.",
    "proposals": {"<proposal id>": {"rewrite": "해당 제안의 근거를 읽고 다시 쓴 설명(선택)"}},
}


class State(TypedDict, total=False):
    params: dict[str, Any]
    entries: list[dict[str, Any]]
    broken_lines: list[str]
    proposals: Annotated[list[dict[str, Any]], operator.add]
    ranked: list[dict[str, Any]]
    stats: dict[str, Any]
    draft: dict[str, Any]
    report_paths: dict[str, str]


def _now(params: dict[str, Any]) -> dt.datetime:
    value = params.get("now")
    return dt.datetime.fromisoformat(value) if value else dt.datetime.now(dt.timezone.utc)


# ── 노드 ────────────────────────────────────────────────────────────────

def n_load(state: State) -> dict[str, Any]:
    loaded = wa.load_entries(Path(state["params"]["workmem"]))
    return {"entries": loaded["entries"], "broken_lines": loaded["broken_lines"]}


def n_promotion(state: State) -> dict[str, Any]:
    return {"proposals": wa.analyze_promotion(state["entries"], now=_now(state["params"]))}


def n_workflow(state: State) -> dict[str, Any]:
    return {"proposals": wa.analyze_workflow(state["entries"], now=_now(state["params"]))}


def n_stale(state: State) -> dict[str, Any]:
    p = state["params"]
    root = Path(p["project_root"]) if p.get("project_root") else None
    return {"proposals": wa.analyze_stale(state["entries"], now=_now(p), project_root=root, stale_days=p.get("stale_days", 30))}


def n_quality(state: State) -> dict[str, Any]:
    p = state["params"]
    return {"proposals": wa.analyze_quality(state["entries"], now=_now(p), stale_days=p.get("stale_days", 30))}


def n_collect(state: State) -> dict[str, Any]:
    p = state["params"]
    return {"ranked": wa.rank(state.get("proposals", []), p.get("max_per_kind")),
            "stats": wa.stats(state["entries"], state.get("broken_lines", []))}


def _draft_pack(state: State) -> dict[str, Any]:
    return {
        "instruction": "아래 결정적 분석 결과를 근거 entry 와 함께 읽고 요약과 제안 문안을 한국어로 쓴다. "
                       "근거에 없는 사실을 만들지 않는다. work-memory 를 수정하지 않는다.",
        "expects": DRAFT_EXPECTS,
        "stats": state["stats"],
        "proposals": [{k: p[k] for k in ("id", "kind", "priority", "title", "why", "suggestion", "evidence", "data")} for p in state["ranked"]],
    }


def n_draft(state: State) -> dict[str, Any]:
    out = Path(state["params"]["out"])
    out.mkdir(parents=True, exist_ok=True)
    pack_path = out / "draft_pack.json"
    pack_path.write_text(json.dumps(_draft_pack(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    value = interrupt({"action": "write_narrative", "reason": "awaiting_draft", "pack": str(pack_path), "expects": DRAFT_EXPECTS})
    return {"draft": value if isinstance(value, dict) else {"summary": str(value)}}


def n_publish(state: State) -> dict[str, Any]:
    p = state["params"]
    out = Path(p["out"])
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": _now(p).isoformat(), "workmem": str(p["workmem"]), "stats": state["stats"],
        "proposals": state["ranked"], "draft": state.get("draft"),
        "params": {k: p.get(k) for k in ("stale_days", "max_per_kind", "project_root")},
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(wa.render_markdown(report), encoding="utf-8")
    return {"report_paths": {"json": str(out / "report.json"), "markdown": str(out / "report.md")}}


def route_after_collect(state: State) -> str:
    return "draft" if (state["params"].get("draft") and _CHECKPOINTED) else "publish"


# ── 그래프 ──────────────────────────────────────────────────────────────

ANALYZERS = ("promotion", "workflow", "stale", "quality")


def build_graph(checkpointer=None):
    global _CHECKPOINTED
    if not LANGGRAPH_AVAILABLE:
        raise RuntimeError("langgraph is not installed; use run() for the linear fallback")
    _CHECKPOINTED = checkpointer is not None
    g = StateGraph(State)
    for name, fn in (("load", n_load), ("promotion", n_promotion), ("workflow", n_workflow), ("stale", n_stale),
                     ("quality", n_quality), ("collect", n_collect), ("draft", n_draft), ("publish", n_publish)):
        g.add_node(name, fn)
    g.add_edge(START, "load")
    for name in ANALYZERS:
        g.add_edge("load", name)
    g.add_edge(list(ANALYZERS), "collect")
    g.add_conditional_edges("collect", route_after_collect, {"draft": "draft", "publish": "publish"})
    g.add_edge("draft", "publish")
    g.add_edge("publish", END)
    return g.compile(checkpointer=checkpointer) if checkpointer is not None else g.compile()


def make_params(workmem: Path, out: Path | None = None, project_root: Path | None = None, **extra: Any) -> dict[str, Any]:
    workmem = Path(workmem)
    now = extra.get("now") or dt.datetime.now(dt.timezone.utc).isoformat()
    default_root = workmem.parent.parent if workmem.name == "work-memory" and workmem.parent.name == "agent-context" else None
    params = {"workmem": str(workmem), "project_root": str(project_root or default_root) if (project_root or default_root) else None,
              "out": str(out or Path("generated/work-memory-analysis") / now[:10]),
              "stale_days": 30, "max_per_kind": 10, "draft": False}
    params.update({k: v for k, v in extra.items() if v is not None})
    params["now"] = now
    return params


def run(workmem: Path, out: Path | None = None, **kwargs: Any) -> State:
    """체크포인터 없이 결정적 분석만 돌려 리포트를 쓴다(모델 요약 없음)."""
    params = make_params(workmem, out, **kwargs)
    params["draft"] = False
    if LANGGRAPH_AVAILABLE:
        return build_graph().invoke({"params": params})
    state: State = {"params": params}
    state.update(n_load(state))
    state["proposals"] = []
    for fn in (n_promotion, n_workflow, n_stale, n_quality):
        state["proposals"] = state["proposals"] + fn(state)["proposals"]
    state.update(n_collect(state))
    state.update(n_publish(state))
    return state


def sqlite_checkpointer(path: str):
    """SQLite 체크포인터(pip install langgraph-checkpoint-sqlite). 프로세스가 끝나도 대기 지점이 남는다."""
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}


def start(thread_id: str, params: dict[str, Any], checkpointer) -> dict[str, Any]:
    """모델 요약 단계(draft)까지 진행하고 멈춘다. 결과에 '__interrupt__' 가 담긴다."""
    return build_graph(checkpointer).invoke({"params": dict(params, draft=True)}, config=_config(thread_id))


def resume(thread_id: str, draft: dict[str, Any], checkpointer) -> dict[str, Any]:
    """control plane 이 쓴 요약({summary, proposals:{id:{rewrite}}})을 받아 리포트를 마무리한다."""
    return build_graph(checkpointer).invoke(Command(resume=draft), config=_config(thread_id))


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze work-memory and write an improvement-proposal report (read-only).")
    ap.add_argument("workmem", nargs="?", type=Path, help="agent-context/work-memory directory")
    ap.add_argument("--out", type=Path, help="report directory (default: generated/work-memory-analysis/<date>)")
    ap.add_argument("--project-root", type=Path, help="project root for path checks (default: parent of agent-context)")
    ap.add_argument("--stale-days", type=int, default=30)
    ap.add_argument("--max-per-kind", type=int, default=10, help="proposals kept per kind (0 = all)")
    ap.add_argument("--draft", action="store_true", help="pause for a control-plane narrative (needs --checkpoint)")
    ap.add_argument("--checkpoint", help="SQLite checkpoint file for --draft / --resume")
    ap.add_argument("--thread", default="wm-analysis")
    ap.add_argument("--resume", metavar="THREAD", help="resume a paused run")
    ap.add_argument("--draft-file", type=Path, help="JSON with the narrative for --resume")
    args = ap.parse_args(argv)

    if args.resume:
        if not (args.checkpoint and args.draft_file):
            ap.error("--resume needs --checkpoint and --draft-file")
        result = resume(args.resume, json.loads(args.draft_file.read_text(encoding="utf-8")), sqlite_checkpointer(args.checkpoint))
    else:
        if not args.workmem:
            ap.error("workmem directory is required")
        if not args.workmem.is_dir():
            ap.error(f"not a directory: {args.workmem}")
        extra = {"stale_days": args.stale_days, "max_per_kind": args.max_per_kind or None, "project_root": args.project_root}
        if args.draft:
            if not (args.checkpoint and LANGGRAPH_AVAILABLE):
                ap.error("--draft needs --checkpoint and langgraph (pip install -r requirements-langgraph.txt)")
            params = make_params(args.workmem, args.out, **extra)
            result = start(args.thread, params, sqlite_checkpointer(args.checkpoint))
        else:
            result = run(args.workmem, args.out, **extra)

    paused = (result.get("__interrupt__") or [None])[0]
    if paused is not None:
        print(json.dumps({"status": "awaiting_draft", "thread": args.thread, **paused.value}, ensure_ascii=False))
        return 0
    print(json.dumps({"status": "done", **result["report_paths"], "proposals": len(result["ranked"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
