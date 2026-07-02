#!/usr/bin/env python3
"""trust_v07 — Trust 계산 + Oracle Decision 제안 (v0.10.0, ROADMAP §8·§9).

    Execution + Knowledge Artifact → Trust Policy → Trust Score
    Artifact Trust + Execution Trust → Oracle → Decision

원칙 (SPEC mso-v0.10.0):
  D-25  Trust는 계산 전용 — TTL에 저장하지 않는다. 산출물은 리포트/JSON뿐.
  D-26  Trust Policy는 YAML로 재정의 가능 (기본 내장). Policy 자체도 Artifact(§4).
  D-27  재현성 — 리포트에 정책 값과 신호 결손(중립값 사용처)을 명시한다.
  D-28  판정(Oracle Decision)은 제안이다 — 확정은 Eval의 oracle 권위.

Usage:
  python trust_v07.py <dir|file.abox.ttl> [...] [--policy policy.yaml]
                      [--json] [--report out.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_v07 import WF, execution_subject, is_v07_graph  # noqa: E402

PROVENANCE_PROPS = (WF.author, WF.version, WF.timestamp, WF.validation, WF.coverage, WF.confidence)
METADATA_PROPS = (WF.method, WF.policy, WF.timestamp)

DEFAULT_POLICY = {
    "artifact": {
        "w_confidence": 0.4,
        "w_validation": 0.2,
        "w_coverage": 0.2,
        "w_completeness": 0.2,
        "neutral": 0.5,           # 미선언 confidence/coverage의 중립 prior
        "evidence_lambda": 0.3,   # 계보 전파 비중
        "evidence_rounds": 3,     # 전파 반복 (순환 안전)
    },
    "execution": {
        "w_subject": 0.6,
        "w_metadata": 0.4,
        "subject_score": {
            "human": 0.95, "system": 0.85, "self": 0.75,
            "workflow": 0.70, "model": 0.65,
        },
    },
    "workflow": {
        "w_consumed": 0.4,   # GIGO — 소비 artifact 최대 가중
        "w_execution": 0.3,
        "w_produced": 0.3,
    },
    "trust_threshold": 0.7,
}


def load_policy(path: Path | None) -> dict:
    policy = json.loads(json.dumps(DEFAULT_POLICY))  # deep copy
    if path is None:
        return policy
    import yaml
    override = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def merge(base: dict, extra: dict):
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = value

    merge(policy, override)
    return policy


def _decimal(g: Graph, node, prop) -> float | None:
    value = g.value(node, prop)
    if isinstance(value, Literal):
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return None
    return None


def _local(node) -> str:
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _streams_by_type(g: Graph) -> dict[str, list[tuple[URIRef, URIRef]]]:
    out: dict[str, list[tuple[URIRef, URIRef]]] = {}
    for stream in g.subjects(RDF.type, WF.Stream):
        stream_type = g.value(stream, WF.streamType)
        source = g.value(stream, WF["from"])
        target = g.value(stream, WF.to)
        if isinstance(stream_type, Literal) and isinstance(source, URIRef) and isinstance(target, URIRef):
            out.setdefault(str(stream_type), []).append((source, target))
    return out


class TrustCalculator:
    def __init__(self, g: Graph, policy: dict):
        self.g = g
        self.policy = policy
        self.streams = _streams_by_type(g)
        self.missing_signals: list[str] = []

    # ── §8 Artifact Trust ────────────────────────────────────────────────

    def artifact_own_trust(self, artifact: URIRef) -> float:
        p = self.policy["artifact"]
        confidence = _decimal(self.g, artifact, WF.confidence)
        coverage = _decimal(self.g, artifact, WF.coverage)
        has_validation = isinstance(self.g.value(artifact, WF.validation), Literal)
        declared = sum(
            1 for prop in PROVENANCE_PROPS
            if isinstance(self.g.value(artifact, prop), Literal)
        )
        completeness = declared / len(PROVENANCE_PROPS)
        if confidence is None:
            self.missing_signals.append(f"artifact {_local(artifact)}: confidence 미선언 → 중립 {p['neutral']}")
        if coverage is None:
            self.missing_signals.append(f"artifact {_local(artifact)}: coverage 미선언 → 중립 {p['neutral']}")
        return (
            p["w_confidence"] * (confidence if confidence is not None else p["neutral"])
            + p["w_validation"] * (1.0 if has_validation else 0.0)
            + p["w_coverage"] * (coverage if coverage is not None else p["neutral"])
            + p["w_completeness"] * completeness
        )

    def artifact_trusts(self) -> dict[URIRef, float]:
        p = self.policy["artifact"]
        artifacts = sorted(self.g.subjects(RDF.type, WF.Artifact), key=str)
        trust = {a: self.artifact_own_trust(a) for a in artifacts}
        own = dict(trust)
        # evidence_of 계보 전파: 출처(from) trust가 산출물(to)에 흐른다 — GIGO
        evidence = self.streams.get("evidence_of", [])
        for _ in range(int(p["evidence_rounds"])):
            updated = dict(trust)
            incoming: dict[URIRef, list[float]] = {}
            for source, target in evidence:
                if source in trust and target in trust:
                    incoming.setdefault(target, []).append(trust[source])
            for target, sources in incoming.items():
                lineage = sum(sources) / len(sources)
                updated[target] = (1 - p["evidence_lambda"]) * own[target] + p["evidence_lambda"] * lineage
            trust = updated
        return trust

    # ── §8 Execution Trust ───────────────────────────────────────────────

    def execution_trust(self, execution: URIRef) -> float:
        p = self.policy["execution"]
        subject = execution_subject(self.g, execution)
        subject_score = p["subject_score"].get(subject, 0.5)
        declared = sum(
            1 for prop in METADATA_PROPS
            if isinstance(self.g.value(execution, prop), Literal)
        )
        metadata = declared / len(METADATA_PROPS)
        if declared == 0:
            self.missing_signals.append(f"execution {_local(execution)}: §7 metadata 전무 (method/policy/timestamp)")
        return p["w_subject"] * subject_score + p["w_metadata"] * metadata

    def execution_trusts(self) -> dict[URIRef, float]:
        return {
            e: self.execution_trust(e)
            for e in sorted(self.g.subjects(RDF.type, WF.Execution), key=str)
        }

    # ── §9 WorkflowGraph Trust + Oracle Decision ─────────────────────────

    def workflow_trusts(
        self, artifact_trust: dict[URIRef, float], execution_trust: dict[URIRef, float]
    ) -> dict[URIRef, dict]:
        p = self.policy["workflow"]
        consumed_by = self.streams.get("consumed_by", [])
        produces_to = self.streams.get("produces_to", [])
        out: dict[URIRef, dict] = {}
        for workflow in sorted(self.g.subjects(WF.workflowType, None), key=str):
            if not isinstance(workflow, URIRef):
                continue
            members = {n for n in self.g.objects(workflow, WF.has) if isinstance(n, URIRef)}
            executions = [execution_trust[m] for m in members if m in execution_trust]
            consumed = [
                artifact_trust[a] for a, e in consumed_by
                if e in members and a in artifact_trust
            ]
            produced = [
                artifact_trust[a] for e, a in produces_to
                if e in members and a in artifact_trust
            ]

            def mean(values: list[float]) -> float | None:
                return sum(values) / len(values) if values else None

            parts = {
                "consumed": (mean(consumed), p["w_consumed"]),
                "execution": (mean(executions), p["w_execution"]),
                "produced": (mean(produced), p["w_produced"]),
            }
            available = {k: v for k, (v, _) in parts.items() if v is not None}
            weight_sum = sum(w for k, (v, w) in parts.items() if v is not None)
            score = (
                sum(v * w for k, (v, w) in parts.items() if v is not None) / weight_sum
                if weight_sum else None
            )
            for key in ("consumed", "produced"):
                if parts[key][0] is None:
                    self.missing_signals.append(
                        f"workflow {_local(workflow)}: {key} artifact 없음 — WorkflowGraph closure 불완전"
                    )
            out[workflow] = {
                "trust": score,
                "components": {k: v for k, v in available.items()},
                "members": len(members),
            }
        return out

    def oracle_decisions(self, workflow_trust: dict[URIRef, dict]) -> list[dict]:
        threshold = self.policy["trust_threshold"]
        decisions = []
        for rail in sorted(self.g.subjects(RDF.type, WF.Rail), key=str):
            if self.g.value(rail, WF.railType) != Literal("measures"):
                continue
            eval_node = self.g.value(rail, WF["from"])
            workflow = self.g.value(rail, WF.to)
            if not isinstance(eval_node, URIRef) or not isinstance(workflow, URIRef):
                continue
            info = workflow_trust.get(workflow, {})
            score = info.get("trust")
            decisions.append({
                "eval": _local(eval_node),
                "workflow": _local(workflow),
                "trust": score,
                "threshold": threshold,
                "suggestion": (
                    "pass" if score is not None and score >= threshold
                    else "fail" if score is not None else "insufficient-signal"
                ),
            })
        return decisions


def compute(paths: list[Path], policy: dict) -> dict:
    g = Graph()
    for path in paths:
        g.parse(str(path), format="turtle")
    if not is_v07_graph(g):
        return {"error": "v0.7 그래프 아님 (Rail/Stream/Execution 없음)"}
    calc = TrustCalculator(g, policy)
    artifact_trust = calc.artifact_trusts()
    execution_trust = calc.execution_trusts()
    workflow_trust = calc.workflow_trusts(artifact_trust, execution_trust)
    decisions = calc.oracle_decisions(workflow_trust)
    workflow_scores = [v["trust"] for v in workflow_trust.values() if v["trust"] is not None]
    return {
        "policy": policy,
        "artifacts": {_local(k): round(v, 4) for k, v in sorted(artifact_trust.items(), key=lambda kv: str(kv[0]))},
        "executions": {_local(k): round(v, 4) for k, v in sorted(execution_trust.items(), key=lambda kv: str(kv[0]))},
        "workflows": {
            _local(k): {**v, "trust": round(v["trust"], 4) if v["trust"] is not None else None}
            for k, v in workflow_trust.items()
        },
        "repository_trust": round(sum(workflow_scores) / len(workflow_scores), 4) if workflow_scores else None,
        "oracle_decisions": decisions,
        "missing_signals": calc.missing_signals,
    }


def render_report(result: dict) -> str:
    lines = [
        "# MSO Trust Report (§8·§9)",
        "",
        "> **Trust는 저장하는 값이 아니라 계산되는 값이다** (D-25). 이 리포트는 generated",
        "> artifact이며 SSOT가 아니다. 같은 그래프 + 같은 정책 = 같은 점수 (D-27).",
        "",
        f"- repository_trust: **{result['repository_trust']}**",
        f"- trust_threshold: {result['policy']['trust_threshold']}",
        "",
        "## WorkflowGraph Trust (§9)",
        "",
        "| workflow | trust | consumed | execution | produced | members |",
        "|---|---|---|---|---|---|",
    ]
    for name, info in result["workflows"].items():
        c = info["components"]
        lines.append(
            f"| `{name}` | {info['trust']} | {round(c['consumed'], 3) if 'consumed' in c else '—'} "
            f"| {round(c['execution'], 3) if 'execution' in c else '—'} "
            f"| {round(c['produced'], 3) if 'produced' in c else '—'} | {info['members']} |"
        )
    lines += ["", "## Oracle Decision 제안 (D-28 — 확정은 Eval의 oracle 권위)", ""]
    if result["oracle_decisions"]:
        lines += ["| eval | workflow | trust | threshold | 제안 |", "|---|---|---|---|---|"]
        for d in result["oracle_decisions"]:
            lines.append(
                f"| `{d['eval']}` | `{d['workflow']}` | {round(d['trust'], 4) if d['trust'] is not None else '—'} "
                f"| {d['threshold']} | **{d['suggestion']}** |"
            )
    else:
        lines.append("- measures rail 없음 — Eval의 평가 단위(WorkflowGraph) 미선언.")
    lines += ["", "## Artifact Trust (§8, evidence 계보 전파 반영)", ""]
    lines += ["| artifact | trust |", "|---|---|"]
    for name, score in result["artifacts"].items():
        lines.append(f"| `{name}` | {score} |")
    lines += ["", "## Execution Trust (§8)", "", "| execution | trust |", "|---|---|"]
    for name, score in result["executions"].items():
        lines.append(f"| `{name}` | {score} |")
    if result["missing_signals"]:
        lines += ["", f"## 신호 결손 ({len(result['missing_signals'])}건 — 중립값 의존, D-27)", ""]
        for signal in result["missing_signals"][:20]:
            lines.append(f"- {signal}")
        if len(result["missing_signals"]) > 20:
            lines.append(f"- … 외 {len(result['missing_signals']) - 20}건")
    lines.append("")
    return "\n".join(lines)


def collect_paths(targets: list[Path]) -> list[Path]:
    """정본 .abox.ttl + sibling .inferred.ttl (v0.8.0 파생 evidence 포함)."""
    paths: list[Path] = []
    for target in targets:
        if target.is_dir():
            paths.extend(sorted(target.rglob("*.abox.ttl")))
            paths.extend(sorted(target.rglob("*.inferred.ttl")))
        elif target.suffix == ".ttl":
            paths.append(target)
            inferred = target.with_name(target.name.replace(".abox.ttl", ".inferred.ttl"))
            if inferred != target and inferred.exists():
                paths.append(inferred)
    seen: set[Path] = set()
    unique = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trust_v07",
                                 description="Trust 계산 + Oracle Decision 제안 (§8·§9)")
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--policy", type=Path, default=None, help="Trust Policy YAML (기본 내장 정책 재정의)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", type=Path, default=None, help="Markdown 리포트 출력 경로")
    args = ap.parse_args(argv)

    targets = [Path(t).resolve() for t in args.targets]
    for t in targets:
        if not t.exists():
            print(f"경로 없음: {t}", file=sys.stderr)
            return 2
    paths = collect_paths(targets)
    if not paths:
        print("계산할 .abox.ttl 없음", file=sys.stderr)
        return 1

    result = compute(paths, load_policy(args.policy))
    if result.get("error"):
        print(f"✗ {result['error']}", file=sys.stderr)
        return 1

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(result), encoding="utf-8")
        print(f"✓ trust report → {args.report}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.report:
        print(f"repository_trust={result['repository_trust']}")
        for d in result["oracle_decisions"]:
            print(f"  oracle: {d['eval']} → {d['workflow']}: {d['suggestion']} (trust={d['trust']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
