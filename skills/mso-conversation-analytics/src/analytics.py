"""
mso-conversation-analytics CLI
사용:
  python src/analytics.py --query all --days 7 --output table
  python src/analytics.py --query reprompt_rate --days 3 --output json
  python src/analytics.py --feedback --days 7
환경변수:
  MSO_TURNS_PATH  turns.jsonl 경로
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from transitions import load_turns, transition_matrix, factored, funnel, reprompt_rate, unresolved
from feedback    import generate_feedback

QUERIES = {
    "transition_matrix": transition_matrix,
    "factored":          factored,
    "funnel":            funnel,
    "reprompt_rate":     reprompt_rate,
    "unresolved":        unresolved,
}


def _print_table(name: str, rows: list[dict]) -> None:
    print(f"\n{'─'*60}")
    print(f"  {name}  ({len(rows)} rows)")
    print(f"{'─'*60}")
    if not rows:
        print("  (empty)")
        return
    headers = list(rows[0].keys())
    col_w = {h: max(len(h), max(len(str(r.get(h, ""))) for r in rows))
             for h in headers}
    header_line = "  " + "  ".join(h.ljust(col_w[h]) for h in headers)
    print(header_line)
    print("  " + "-" * (len(header_line) - 2))
    for row in rows:
        print("  " + "  ".join(str(row.get(h, "")).ljust(col_w[h]) for h in headers))


def main() -> None:
    parser = argparse.ArgumentParser(description="MSO Conversation Analytics")
    parser.add_argument("--query",    choices=[*QUERIES, "all"],
                        help="실행할 분석 함수")
    parser.add_argument("--feedback", action="store_true",
                        help="환류 보고서 생성 (JSON 출력)")
    parser.add_argument("--days",     type=int, default=7,
                        help="분석 기간 (일, 기본값: 7)")
    parser.add_argument("--output",   choices=["json", "table"], default="table",
                        help="출력 형식")
    args = parser.parse_args()

    if not args.query and not args.feedback:
        parser.print_help()
        sys.exit(1)

    con = load_turns()

    if args.feedback:
        report = generate_feedback(con, days=args.days)
        print(json.dumps(report, ensure_ascii=False, indent=2,
                         default=str))
        return

    targets = (list(QUERIES.items()) if args.query == "all"
               else [(args.query, QUERIES[args.query])])

    if args.output == "json":
        result = {}
        for name, fn in targets:
            result[name] = fn(con, days=args.days)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        for name, fn in targets:
            _print_table(name, fn(con, days=args.days))


if __name__ == "__main__":
    main()
