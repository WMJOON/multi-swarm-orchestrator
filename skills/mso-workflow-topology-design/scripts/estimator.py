#!/usr/bin/env python3
# estimator.py
"""
Semantic Control Estimator (v0.1)

Purpose
- Compare two Canonical Outputs (normalized JSON) and estimate:
  - theta_gt_actual: proxy for semantic entropy (structural uncertainty / openness)
  - delta_entropy: change vs previous state
  - delta_rsv: incremental RSV contribution (decision-question closure based)
  - redundancy: flag when "information grew" but "semantic space didn't"

Design principles
- Pure function style (same input -> same output)
- No LLM calls, no external APIs
- Robust to partial/missing fields in normalized JSON
- Works with "canonical representation" where lists of items exist:
  decision_questions, claims, assumptions, constraints, risks, tradeoffs

Input formats
- JSON file containing:
  {
    "normalized_output": {...},
    "metrics": {... optional ...}
  }
  OR directly the normalized_output object.

Recommended minimal normalized_output schema:
{
  "decision_questions":[{"id":"DQ1","question":"...","status":"open|partial|closed","closure_strength":"strong|partial|weak"}],
  "claims":[{"id":"C1","text":"...","type":"fact|interpretation|recommendation","source":"..."}],
  "assumptions":[{"id":"A1","text":"..."}],
  "constraints":[{"id":"K1","text":"..."}],
  "risks":[{"id":"R1","text":"...","severity":"low|med|high"}],
  "tradeoffs":[{"id":"T1","text":"..."}]
}

CLI examples
- Compare two JSON files:
  python estimator.py --prev prev.json --curr curr.json --rsv-acc 2.0 --expected-theta 0.35 --rsv-total 6.5

- Read prev/curr from stdin (optional):
  cat curr.json | python estimator.py --prev prev.json --stdin-curr
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_WEIGHTS = {
    # theta proxy = w_new * new_units + w_open * open_ratio + w_var * type_var - w_red * redundancy_ratio
    "w_new": 0.35,
    "w_open": 0.35,
    "w_var": 0.20,
    "w_red": 0.30,
}

DEFAULT_EPSILON = 0.02  # for "entropy change is negligible"
DEFAULT_REDUNDANCY_THRESHOLD = 0.75  # redundancy_ratio above this is "mostly rephrase"
DEFAULT_MIN_NEW_UNITS_FOR_PROGRESS = 1  # if no new semantic units and delta small -> redundancy


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    return str(x)


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    # keep alnum + basic punctuation; drop the rest
    s = re.sub(r"[^a-z0-9가-힣\s\.\,\-\_\:\;\(\)\/]", "", s)
    return s.strip()


def _tokenize(s: str) -> Set[str]:
    s = _normalize_text(s)
    # simple tokenization; can be replaced later with better rules
    tokens = re.split(r"[\s\.,;:\(\)\/\-_]+", s)
    return {t for t in tokens if t}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return inter / union if union else 0.0


def _extract_normalized_output(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Accept either full wrapper or just normalized_output
    if "normalized_output" in payload and isinstance(payload["normalized_output"], dict):
        return payload["normalized_output"]
    return payload


def _item_id(item: Any, fallback_prefix: str, idx: int) -> str:
    if isinstance(item, dict):
        for key in ("id", "key", "code"):
            if key in item and _safe_str(item[key]).strip():
                return _safe_str(item[key]).strip()
    return f"{fallback_prefix}_{idx}"


def _item_text(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("text", "content", "question", "summary", "statement", "value"):
            if key in item and _safe_str(item[key]).strip():
                return _safe_str(item[key])
        # fall back: stringify dict
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    return _safe_str(item)


def _item_type(item: Any, default_type: str) -> str:
    if isinstance(item, dict):
        t = _safe_str(item.get("type", "")).strip()
        return t if t else default_type
    return default_type


def _dq_status(item: Any) -> str:
    if isinstance(item, dict):
        s = _safe_str(item.get("status", "")).lower().strip()
        if s in {"open", "partial", "closed"}:
            return s
        # allow boolean-ish
        if s in {"done", "resolved"}:
            return "closed"
    return "open"


def _dq_strength(item: Any) -> float:
    """
    Map closure_strength to RSV increment weights.
    """
    if isinstance(item, dict):
        cs = _safe_str(item.get("closure_strength", "")).lower().strip()
        if cs == "strong":
            return 1.0
        if cs == "partial":
            return 0.5
        if cs == "weak":
            return 0.25
    # default if marked closed but no strength:
    return 1.0


@dataclass(frozen=True)
class CanonicalIndex:
    # keyed by canonical id -> (type, token_set)
    units: Dict[str, Tuple[str, Set[str]]]
    dq_status: Dict[str, str]


def build_index(norm: Dict[str, Any]) -> CanonicalIndex:
    units: Dict[str, Tuple[str, Set[str]]] = {}
    dq_status: Dict[str, str] = {}

    sections = [
        ("decision_questions", "dq"),
        ("claims", "claim"),
        ("assumptions", "assumption"),
        ("constraints", "constraint"),
        ("risks", "risk"),
        ("tradeoffs", "tradeoff"),
    ]

    for section_name, default_type in sections:
        items = _safe_list(norm.get(section_name))
        for i, item in enumerate(items):
            cid = f"{section_name}:{_item_id(item, default_type, i)}"
            t = _item_type(item, default_type)
            text = _item_text(item)
            tokens = _tokenize(text)
            units[cid] = (t, tokens)
            if section_name == "decision_questions":
                dq_status[cid] = _dq_status(item)

    return CanonicalIndex(units=units, dq_status=dq_status)


def _match_best(curr_tokens: Set[str], prev_units: Dict[str, Tuple[str, Set[str]]]) -> Tuple[Optional[str], float]:
    """
    Find best match in prev by Jaccard similarity.
    Returns (best_id, best_score).
    """
    best_id = None
    best_score = 0.0
    for pid, (_ptype, ptokens) in prev_units.items():
        score = jaccard(curr_tokens, ptokens)
        if score > best_score:
            best_score = score
            best_id = pid
    return best_id, best_score


@dataclass
class EstimateResult:
    theta_gt_actual: float
    delta_entropy: float
    delta_rsv: float
    redundancy: bool
    diagnostics: Dict[str, Any]


def estimate(
    prev_norm: Dict[str, Any],
    curr_norm: Dict[str, Any],
    rsv_accumulated: float = 0.0,
    expected_theta_gt: Optional[float] = None,
    rsv_total: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
    epsilon: float = DEFAULT_EPSILON,
    redundancy_threshold: float = DEFAULT_REDUNDANCY_THRESHOLD,
    min_new_units_for_progress: int = DEFAULT_MIN_NEW_UNITS_FOR_PROGRESS,
) -> EstimateResult:
    """
    Core estimator.
    - prev_norm / curr_norm: canonical normalized_output dicts
    - rsv_accumulated: previous accumulated RSV (for convenience in diagnostics; not required)
    - expected_theta_gt / rsv_total: optional targets to include in diagnostics
    """

    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    prev_idx = build_index(prev_norm or {})
    curr_idx = build_index(curr_norm or {})

    prev_units = prev_idx.units
    curr_units = curr_idx.units

    # 1) New semantic units vs "rephrases"
    new_units: List[str] = []
    rephrases: List[Tuple[str, str, float]] = []  # (curr_id, prev_id, sim)

    # We treat a curr unit as "new" if it doesn't closely match any prev unit
    # Threshold is conservative; tune later.
    SIM_NEW_THRESHOLD = 0.62

    for cid, (_ctype, ctokens) in curr_units.items():
        if not prev_units:
            new_units.append(cid)
            continue
        best_id, best_score = _match_best(ctokens, prev_units)
        if best_id is None or best_score < SIM_NEW_THRESHOLD:
            new_units.append(cid)
        else:
            rephrases.append((cid, best_id, best_score))

    new_units_count = len(new_units)
    rephrase_count = len(rephrases)
    total_curr_units = max(1, len(curr_units))
    redundancy_ratio = rephrase_count / total_curr_units

    # 2) Open ratio (proxy for "unclosed meaning space")
    # - We only look at decision_questions. If many remain open, entropy stays high.
    dq_total = max(1, len(curr_idx.dq_status))
    dq_open = sum(1 for s in curr_idx.dq_status.values() if s == "open")
    dq_partial = sum(1 for s in curr_idx.dq_status.values() if s == "partial")
    dq_closed = sum(1 for s in curr_idx.dq_status.values() if s == "closed")

    # openness proxy: open + 0.5*partial
    open_ratio = (dq_open + 0.5 * dq_partial) / dq_total

    # 3) Type variance proxy (how many unit types are present)
    types_present = {t for (t, _tok) in curr_units.values()}
    # normalize by max types
    max_types = 6
    type_variance = min(1.0, len(types_present) / max_types)

    # 4) Compute theta proxy (0..1-ish)
    # Use saturating transform so counts don't explode.
    def sat(x: float) -> float:
        return 1.0 - math.exp(-x)

    new_component = sat(new_units_count / 4.0)  # 4 new units ~= noticeable jump
    theta = (
        w["w_new"] * new_component
        + w["w_open"] * open_ratio
        + w["w_var"] * type_variance
        - w["w_red"] * redundancy_ratio
    )
    # clip
    theta = max(0.0, min(1.0, theta))

    # 5) delta_entropy vs previous theta proxy
    # Estimate prev theta similarly but cheaper using only prev index
    prev_types_present = {t for (t, _tok) in prev_units.values()}
    prev_type_variance = min(1.0, len(prev_types_present) / max_types)

    prev_dq_total = max(1, len(prev_idx.dq_status))
    prev_dq_open = sum(1 for s in prev_idx.dq_status.values() if s == "open")
    prev_dq_partial = sum(1 for s in prev_idx.dq_status.values() if s == "partial")
    prev_open_ratio = (prev_dq_open + 0.5 * prev_dq_partial) / prev_dq_total

    # For prev_new_component, we approximate with its own size; we don't compare to older history here.
    prev_new_component = sat(len(prev_units) / 12.0)  # heuristic baseline
    prev_redundancy_ratio = 0.0  # not defined without older snapshot

    prev_theta = (
        w["w_new"] * prev_new_component
        + w["w_open"] * prev_open_ratio
        + w["w_var"] * prev_type_variance
        - w["w_red"] * prev_redundancy_ratio
    )
    prev_theta = max(0.0, min(1.0, prev_theta))

    delta_entropy = theta - prev_theta

    # 6) RSV increment (delta_rsv) based on newly closed decision questions
    delta_rsv = 0.0
    newly_closed: List[str] = []
    newly_partial: List[str] = []

    prev_dq = prev_idx.dq_status
    # Need access to strength in current DQ objects:
    curr_dq_items = _safe_list(curr_norm.get("decision_questions"))

    # map curr dq id -> item for strength lookup
    curr_dq_item_by_cid: Dict[str, Any] = {}
    for i, item in enumerate(curr_dq_items):
        cid = f"decision_questions:{_item_id(item, 'dq', i)}"
        curr_dq_item_by_cid[cid] = item

    for cid, status in curr_idx.dq_status.items():
        prev_status = prev_dq.get(cid, "open")
        if status == "closed" and prev_status != "closed":
            newly_closed.append(cid)
            delta_rsv += _dq_strength(curr_dq_item_by_cid.get(cid, {}))
        elif status == "partial" and prev_status == "open":
            newly_partial.append(cid)
            # partial closure default weight
            delta_rsv += 0.5

    rsv_acc_next = rsv_accumulated + delta_rsv

    # 7) Redundancy flag: "quantity grew but semantic space didn't"
    # - no meaningful new units
    # - entropy change negligible
    # - redundancy ratio high
    redundancy = (
        new_units_count < min_new_units_for_progress
        and abs(delta_entropy) < epsilon
        and redundancy_ratio >= redundancy_threshold
    )

    diagnostics = {
        "counts": {
            "prev_units": len(prev_units),
            "curr_units": len(curr_units),
            "new_units": new_units_count,
            "rephrases": rephrase_count,
            "dq_total": dq_total,
            "dq_open": dq_open,
            "dq_partial": dq_partial,
            "dq_closed": dq_closed,
        },
        "ratios": {
            "redundancy_ratio": round(redundancy_ratio, 4),
            "open_ratio": round(open_ratio, 4),
            "type_variance": round(type_variance, 4),
        },
        "signals": {
            "expected_theta_gt": expected_theta_gt,
            "rsv_total": rsv_total,
            "rsv_accumulated_prev": rsv_accumulated,
            "rsv_accumulated_next": rsv_acc_next,
        },
        "debug_lists": {
            "new_units": new_units[:20],
            "newly_closed_dq": newly_closed,
            "newly_partial_dq": newly_partial,
            "top_rephrases": sorted(rephrases, key=lambda x: x[2], reverse=True)[:10],
        },
        "parameters": {
            "weights": w,
            "epsilon": epsilon,
            "redundancy_threshold": redundancy_threshold,
            "sim_new_threshold": SIM_NEW_THRESHOLD,
        },
    }

    return EstimateResult(
        theta_gt_actual=theta,
        delta_entropy=delta_entropy,
        delta_rsv=delta_rsv,
        redundancy=redundancy,
        diagnostics=diagnostics,
    )


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _read_stdin_json() -> Dict[str, Any]:
    text = ""
    try:
        text = input()
        # if piped multi-line, continue reading
        while True:
            line = input()
            text += "\n" + line
    except EOFError:
        pass
    text = text.strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("STDIN JSON root must be an object")
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", required=True, help="Prev JSON file (wrapper or normalized_output)")
    ap.add_argument("--curr", help="Curr JSON file (wrapper or normalized_output)")
    ap.add_argument("--stdin-curr", action="store_true", help="Read curr JSON from stdin instead of file")

    ap.add_argument("--rsv-acc", type=float, default=0.0, help="Previously accumulated RSV")
    ap.add_argument("--expected-theta", type=float, default=None, help="Expected theta_gt upper bound for this node")
    ap.add_argument("--rsv-total", type=float, default=None, help="RSV total required for workflow goal")

    ap.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON)
    ap.add_argument("--redundancy-threshold", type=float, default=DEFAULT_REDUNDANCY_THRESHOLD)

    args = ap.parse_args()

    prev_payload = _load_json(args.prev)
    curr_payload = _read_stdin_json() if args.stdin_curr else _load_json(args.curr) if args.curr else {}

    prev_norm = _extract_normalized_output(prev_payload)
    curr_norm = _extract_normalized_output(curr_payload)

    res = estimate(
        prev_norm=prev_norm,
        curr_norm=curr_norm,
        rsv_accumulated=args.rsv_acc,
        expected_theta_gt=args.expected_theta,
        rsv_total=args.rsv_total,
        epsilon=args.epsilon,
        redundancy_threshold=args.redundancy_threshold,
    )

    out = {
        "metrics": {
            "theta_gt_actual": round(res.theta_gt_actual, 6),
            "delta_entropy": round(res.delta_entropy, 6),
            "delta_rsv": round(res.delta_rsv, 6),
            "redundancy": res.redundancy,
        },
        "diagnostics": res.diagnostics,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
