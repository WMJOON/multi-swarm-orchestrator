#!/usr/bin/env python3
"""
Compute APO signals from LLM-as-a-judge labels vs human labels.

Usage:
  python3 compute_apo_signals.py \
    --llm-labels llm_labels.jsonl \
    --human-labels human_labels.jsonl \
    --output apo_signals.json [--top-n 10] [--baseline-disagreement 0.0]

Input JSONL formats:
  llm_labels:   {"id": "...", "class": "...", "confidence": 0.85, "margin": 0.4}
  human_labels: {"id": "...", "reviewed_class": "..."}
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def compute_signals(llm: list[dict], human: list[dict], top_n: int, baseline: float) -> dict:
    human_map = {r["id"]: r["reviewed_class"] for r in human}

    matched = [(r, human_map[r["id"]]) for r in llm if r["id"] in human_map]
    if not matched:
        return {"error": "no matched ids between llm and human labels"}

    total = len(matched)
    disagree_count = sum(1 for r, h in matched if r["class"] != h)
    disagreement_rate = disagree_count / total

    low_confidence = sum(1 for r, _ in matched if r.get("confidence", 1.0) < 0.5)
    low_margin = sum(1 for r, _ in matched if r.get("margin", 1.0) < 0.2)

    # Per-class confusion score
    class_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "disagree": 0, "low_conf": 0, "low_margin": 0})
    for r, h in matched:
        cls = r["class"]
        class_stats[cls]["total"] += 1
        if r["class"] != h:
            class_stats[cls]["disagree"] += 1
        if r.get("confidence", 1.0) < 0.5:
            class_stats[cls]["low_conf"] += 1
        if r.get("margin", 1.0) < 0.2:
            class_stats[cls]["low_margin"] += 1

    confusion_scores = []
    for cls, s in class_stats.items():
        if s["total"] == 0:
            continue
        score = (
            (s["disagree"] / s["total"]) * 0.4
            + (s["low_conf"] / s["total"]) * 0.4
            + (s["low_margin"] / s["total"]) * 0.2
        )
        confusion_scores.append({"class": cls, "confusion_score": round(score, 4), **s})

    confusion_scores.sort(key=lambda x: x["confusion_score"], reverse=True)

    # Safety gate (4 conditions)
    mean_conf = sum(r.get("confidence", 1.0) for r, _ in matched) / total
    confs = sorted(r.get("confidence", 1.0) for r, _ in matched)
    worst_p10 = confs[int(total * 0.1)] if total >= 10 else confs[0]

    gate = {
        "delta_ok": mean_conf >= baseline - 0.05,
        "worst_p10_ok": worst_p10 >= baseline - 0.10,
        "deterioration_ok": (low_confidence / total) <= 0.05,
        "disagreement_ok": disagreement_rate <= baseline + 0.05,
    }
    gate["all_pass"] = all(gate.values())

    if gate["all_pass"]:
        recommended = "skip"
    elif disagreement_rate >= 0.15:
        recommended = "run_apo"
    else:
        recommended = "monitor"

    return {
        "total_matched": total,
        "disagreement_rate": round(disagreement_rate, 4),
        "mean_confidence": round(mean_conf, 4),
        "worst_p10_confidence": round(worst_p10, 4),
        "deterioration_rate": round(low_confidence / total, 4),
        "safety_gate": gate,
        "top_confused_classes": confusion_scores[:top_n],
        "recommended_decision": recommended,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm-labels", required=True)
    parser.add_argument("--human-labels", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--baseline-disagreement", type=float, default=0.0,
                        help="Previous round disagreement_rate as baseline")
    args = parser.parse_args()

    llm = load_jsonl(args.llm_labels)
    human = load_jsonl(args.human_labels)
    result = compute_signals(llm, human, args.top_n, args.baseline_disagreement)

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
