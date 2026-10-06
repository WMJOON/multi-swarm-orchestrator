#!/usr/bin/env python3
"""work-memory 결정적 분석기.

agent-context/work-memory 의 jsonl entry 를 읽기 전용으로 분석해 **제안(proposal)** 을 만든다.
LLM 을 쓰지 않는다. 같은 입력이면 같은 제안이 나온다(재현 가능). 각 제안은 근거 entry id 를 붙인다.

분석 4종:
  promotion  회고 승격 후보  — 반복되는 IN/TS 를 EP 로, EP 군을 PT 로, 안정된 PT 를 PR 로 올릴 후보
  workflow   workflow 개선안 — 재발하는 root cause·모듈 핫스팟에서 게이트/테스트/훅 후보
  stale      낡은 결정·교훈 — 사라진 경로를 인용하는 결정, 릴리스 뒤 재확인 없는 결정, supersede 누락 후보
  quality    기록 누락·품질  — 끊긴 관계, 상태 불일치, 빠진 필수 필드, 태그·어휘 드리프트

work-memory 에는 절대 쓰지 않는다. 결과는 호출자가 리포트로 낸다.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

KINDS = ("promotion", "workflow", "stale", "quality")
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# entry id 접두사 → type
PREFIX_TYPE = {
    "IN": "issue-note", "AD": "agent-decision", "UD": "user-decision", "AR": "alternatives-record",
    "TS": "trouble-shooting", "RN": "release-note", "EP": "episode", "PT": "pattern", "PR": "principle",
}
RECORD_DIRS = ("track-record", "insight-record", "release-record")
ID_RE = re.compile(r"\b(IN|AD|UD|AR|TS|RN|EP|PT|PR)-\d{4,}\b")
PATH_RE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})(?![\w/])")
GENERIC_TAGS = {"auditlog", "bash", "agent", "ontology", "law", "gap", "modeling"}
SEVERITY_VOCAB = {"low", "medium", "high"}
STATUS_VOCAB = {"open", "fixing", "partially-resolved", "resolved"}


# ── 적재 ────────────────────────────────────────────────────────────────

def load_entries(workmem: Path) -> dict[str, Any]:
    """track/insight/release-record 의 entry 를 모두 읽는다. 깨진 줄은 건너뛰고 기록해 둔다."""
    entries: list[dict[str, Any]] = []
    broken: list[str] = []
    for directory in RECORD_DIRS:
        for path in sorted((workmem / directory).glob("*.jsonl")) if (workmem / directory).is_dir() else []:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    broken.append(f"{path.name}:{number}")
                    continue
                if isinstance(row, dict) and row.get("id"):
                    row.setdefault("metadata", {})
                    row["metadata"] = row["metadata"] or {}
                    row["relations"] = [r for r in (row.get("relations") or []) if isinstance(r, dict)]
                    entries.append(row)
    return {"entries": entries, "broken_lines": broken}


def _days(value: str | None, now: dt.datetime) -> float | None:
    if not value:
        return None
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (now - when).total_seconds() / 86400


def _by_type(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry.get("type") or PREFIX_TYPE.get(str(entry["id"]).split("-")[0], "?")].append(entry)
    return grouped


def _out_edges(entry: dict[str, Any], *types: str) -> list[str]:
    return [r["target"] for r in entry["relations"] if r.get("type") in types and r.get("target")]


def _text_of(entry: dict[str, Any]) -> str:
    meta = entry["metadata"]
    parts = [entry.get("title", ""), entry.get("text", "")]
    for key in ("root_cause", "fix_summary", "rationale", "what_happened", "root_shape"):
        value = meta.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(p for p in parts if p)


# ── 어휘 유사도 (TF-IDF cosine, 외부 의존 없음) ─────────────────────────

_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9_]{2,}")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        if re.match(r"[가-힣]", raw):
            out.extend(raw[i:i + 2] for i in range(len(raw) - 1))  # 한글은 음절 bigram (조사 영향을 줄인다)
        else:
            out.append(raw.lower())
    return out


def _vectors(texts: dict[str, str]) -> dict[str, dict[str, float]]:
    docs = {key: Counter(_tokens(text)) for key, text in texts.items()}
    df: Counter[str] = Counter()
    for counts in docs.values():
        df.update(counts.keys())
    n = max(len(docs), 1)
    vectors: dict[str, dict[str, float]] = {}
    for key, counts in docs.items():
        vec = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 0.5)) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors[key] = {t: v / norm for t, v in vec.items()}
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def cluster(texts: dict[str, str], threshold: float) -> list[list[str]]:
    """single-link 군집. 입력 순서와 무관하게 결정적이도록 키를 정렬해 처리한다."""
    keys = sorted(texts)
    vectors = _vectors(texts)
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if _cosine(vectors[a], vectors[b]) >= threshold:
                parent[find(b)] = find(a)
    groups: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        groups[find(k)].append(k)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def _norm_tag(tag: str) -> str:
    return re.sub(r"[-_\s]+", "-", tag.strip().lower())


def _proposal(kind: str, code: str, priority: str, title: str, why: str, suggestion: str, evidence: list[str], **data: Any) -> dict[str, Any]:
    return {"id": f"{kind}:{code}", "kind": kind, "priority": priority, "title": title, "why": why,
            "suggestion": suggestion, "evidence": sorted(set(evidence)), "data": data}


# ── 1. 회고 승격 후보 ───────────────────────────────────────────────────

def analyze_promotion(entries: list[dict[str, Any]], *, now: dt.datetime, threshold: float = 0.18, min_cluster: int = 3) -> list[dict[str, Any]]:
    by = _by_type(entries)
    covered: set[str] = set()
    for entry in by.get("episode", []) + by.get("pattern", []) + by.get("principle", []):
        covered.update(t for t in _out_edges(entry, "references", "analyzed-in", "generalized-in", "shows-pattern", "crystallized-in"))
        meta = entry["metadata"]
        for key in ("spans", "instances", "sources", "crystallized_from", "evidence"):
            value = meta.get(key)
            if isinstance(value, list):
                covered.update(str(v) for v in value)
            elif isinstance(value, str):
                covered.update(ID_RE.findall(value))
        covered.update(m.group(0) for m in ID_RE.finditer(_text_of(entry)))
    out: list[dict[str, Any]] = []

    # (a) 아직 회고되지 않은 TS/IN 군집 → EP 후보
    pool = {e["id"]: _text_of(e) for e in by.get("trouble-shooting", []) + by.get("issue-note", []) if e["id"] not in covered}
    for group in cluster(pool, threshold):
        if len(group) < min_cluster:
            continue
        members = [e for e in entries if e["id"] in group]
        tags = Counter(_norm_tag(t) for e in members for t in e.get("tags", []) if _norm_tag(t) not in GENERIC_TAGS)
        label = ", ".join(t for t, _ in tags.most_common(3)) or "공통 태그 없음"
        out.append(_proposal(
            "promotion", f"EP:{sorted(group)[0]}", "high" if len(group) >= 5 else "medium",
            f"회고되지 않은 유사 사건 {len(group)}건 → episode 후보 ({label})",
            "비슷한 주제의 IN/TS 가 episode 로 회고되지 않았다. 사건이 일단락됐다면 EP 로 남겨 반복을 드러낼 수 있다.",
            "모델 요약으로 trigger·what_happened·lessons 를 정리해 EP 를 만들고 TS 에 analyzed-in 으로 연결한다.",
            group, size=len(group), tags=[t for t, _ in tags.most_common(5)],
        ))

    # (b) 비슷한 EP 군 → PT 후보
    covered_by_pt = {t for p in by.get("pattern", []) for t in _out_edges(p, "references", "generalized-in")}
    for p in by.get("pattern", []):
        value = p["metadata"].get("instances")
        if isinstance(value, list):
            covered_by_pt.update(str(v) for v in value)
    eps = {e["id"]: _text_of(e) for e in by.get("episode", []) if e["id"] not in covered_by_pt}
    for group in cluster(eps, threshold):
        if len(group) >= 2:
            out.append(_proposal(
                "promotion", f"PT:{sorted(group)[0]}", "high",
                f"비슷한 episode {len(group)}건이 pattern 으로 일반화되지 않았다",
                "EP 가 여러 개 쌓였고 서로 어휘가 가깝다. 반복되는 root_shape 가 있을 수 있다.",
                "공통 root_shape 와 countermeasures 를 추출해 PT 를 만들고 EP 에 generalized-in 으로 연결한다.",
                group, size=len(group),
            ))

    # (c) 응축되지 않은 PT → PR 후보
    for p in by.get("pattern", []):
        if _out_edges(p, "crystallized-in"):
            continue
        instances = p["metadata"].get("instances") or []
        count = len(instances) if isinstance(instances, list) else 0
        if count >= 3:
            out.append(_proposal(
                "promotion", f"PR:{p['id']}", "medium", f"{p['id']} 는 인스턴스 {count}건으로 안정됐지만 principle 이 없다",
                "인스턴스가 3건 이상 쌓인 pattern 은 재사용 가능한 원칙으로 응축할 수 있다.",
                "체크리스트 형태의 PR 을 만들고 PT 에 crystallized-in 으로 연결한다.", [p["id"]] + [str(i) for i in instances],
            ))
    return out


# ── 2. workflow 개선안 ──────────────────────────────────────────────────

def analyze_workflow(entries: list[dict[str, Any]], *, now: dt.datetime, threshold: float = 0.18) -> list[dict[str, Any]]:
    by = _by_type(entries)
    out: list[dict[str, Any]] = []

    # (a) 같은 root cause 가 반복되는 TS → 재발 방지 장치(게이트/테스트/훅) 후보
    causes = {e["id"]: str(e["metadata"].get("root_cause") or "") for e in by.get("trouble-shooting", []) if e["metadata"].get("root_cause")}
    pt_text = " ".join(_text_of(p) + " " + json.dumps(p["metadata"].get("countermeasures", ""), ensure_ascii=False) for p in by.get("pattern", []))
    for group in cluster(causes, threshold):
        if len(group) < 2:
            continue
        members = [e for e in by["trouble-shooting"] if e["id"] in group]
        modules = Counter(_norm_tag(str(e["metadata"].get("module") or "-")) for e in members)
        already = sum(1 for tid in group if tid in pt_text)
        out.append(_proposal(
            "workflow", f"cause:{sorted(group)[0]}", "high" if len(group) >= 4 else "medium",
            f"같은 root cause 로 해결된 TS {len(group)}건 (모듈: {', '.join(m for m, _ in modules.most_common(2))})",
            "비슷한 원인이 반복해서 사후 해결됐다. 사후 대응이 아니라 사전 차단 장치가 없다는 신호다."
            + (f" 이 중 {already}건은 pattern 에 이미 언급돼 있다." if already else ""),
            "원인을 막는 결정적 게이트(검증 스크립트·테스트)나 hook 을 workflow 의 해당 단계에 추가한다. 제안 근거로 root_cause 목록을 쓴다.",
            group, size=len(group), root_causes=[causes[i][:90] for i in sorted(group)[:4]],
        ))

    # (b) 모듈 핫스팟: 열린·고위험 issue 가 몰린 모듈
    modules: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"open": [], "high": [], "all": []})
    for e in by.get("issue-note", []):
        if not e["metadata"].get("module"):
            continue  # 모듈 미지정은 핫스팟이 아니라 기록 품질 문제(quality:module-missing)
        module = _norm_tag(str(e["metadata"]["module"]))  # korean_tax / korean-tax 표기 차이를 합친다
        modules[module]["all"].append(e["id"])
        if e["metadata"].get("status") in {"open", "fixing", "partially-resolved"}:
            modules[module]["open"].append(e["id"])
            if str(e["metadata"].get("severity")) in {"high", "major"}:
                modules[module]["high"].append(e["id"])
    for module, info in modules.items():
        if len(info["open"]) >= 5 or (len(info["open"]) >= 3 and len(info["high"]) >= 3):
            out.append(_proposal(
                "workflow", f"hotspot:{module}", "high" if len(info["high"]) >= 3 else "medium",
                f"모듈 '{module}' 에 열린 issue {len(info['open'])}건 (고위험 {len(info['high'])}건)",
                "한 모듈에 미해결 issue 가 몰려 있다. 해당 모듈의 workflow 단계에 게이트나 검토 노드가 부족할 수 있다.",
                "열린 issue 를 root cause 로 묶어 해당 모듈 workflow 에 검증 노드 또는 되돌림 루프를 추가할지 검토한다.",
                info["open"], open=len(info["open"]), high=len(info["high"]), total=len(info["all"]),
            ))

    # (c) 되돌림: 같은 모듈에서 issue 가 resolve 된 뒤 다시 열림(같은 제목 유사) → 검증 누락 신호
    resolved = {e["id"]: _text_of(e) for e in by.get("issue-note", []) if e["metadata"].get("status") == "resolved"}
    reopened = {e["id"]: _text_of(e) for e in by.get("issue-note", []) if e["metadata"].get("status") in {"open", "fixing"}}
    if resolved and reopened:
        vectors = _vectors({**{f"r:{k}": v for k, v in resolved.items()}, **{f"o:{k}": v for k, v in reopened.items()}})
        pairs = []
        for o in sorted(reopened):
            best = max(((_cosine(vectors[f"o:{o}"], vectors[f"r:{r}"]), r) for r in resolved), default=(0.0, ""))
            if best[0] >= 0.6:
                pairs.append((o, best[1], best[0]))
        if pairs:
            out.append(_proposal(
                "workflow", "recurrence", "medium",
                f"해결된 issue 와 거의 같은 issue 가 다시 열려 있다 ({len(pairs)}쌍)",
                "해결됐다고 닫은 문제가 비슷한 형태로 다시 올라왔다. 해결 시 재발 방지 검증이 빠졌을 수 있다.",
                "각 쌍의 해결 TS 에 회귀 테스트가 있는지 확인하고, 없으면 테스트 또는 게이트를 추가한다.",
                [x for p in pairs for x in p[:2]], pairs=[{"open": o, "resolved": r, "similarity": round(s, 2)} for o, r, s in pairs[:10]],
            ))
    return out


# ── 3. 낡은 결정·교훈 ───────────────────────────────────────────────────

def analyze_stale(entries: list[dict[str, Any]], *, now: dt.datetime, project_root: Path | None, stale_days: int = 30) -> list[dict[str, Any]]:
    by = _by_type(entries)
    out: list[dict[str, Any]] = []
    decisions = by.get("user-decision", []) + by.get("agent-decision", [])

    # (a) 결정이 인용한 경로가 사라졌다
    if project_root is not None:
        gone: dict[str, list[str]] = defaultdict(list)
        for e in decisions + by.get("principle", []) + by.get("pattern", []):
            for raw in PATH_RE.findall(_text_of(e)):
                if raw.startswith(("http", "www.")) or "://" in raw or raw.startswith("agent-context/work-memory"):
                    continue
                if any(ch in raw for ch in "*{}<>$") or raw.count("/") < 1:
                    continue
                if not (project_root / raw.split("/", 1)[0]).is_dir():
                    continue  # 최상위 디렉터리가 없으면 외부 경로(다른 스킬·모델 ID 등)일 가능성이 커서 제외한다
                if not (project_root / raw).exists():
                    gone[e["id"]].append(raw)
        if gone:
            out.append(_proposal(
                "stale", "missing-paths", "medium",
                f"결정·교훈 {len(gone)}건이 지금 존재하지 않는 경로를 인용한다",
                "인용한 파일·디렉터리가 사라졌거나 이름이 바뀌었다. 결정의 전제가 바뀌었을 수 있다.",
                "각 entry 를 열어 경로가 이동한 것이면 relations(supersedes/refines)나 새 entry 로 갱신하고, 전제가 무효면 invalidated-by 를 기록한다.",
                list(gone), paths={k: v[:3] for k, v in sorted(gone.items())[:15]},
            ))

    # (b) 릴리스 뒤에 재확인되지 않은 결정
    releases = sorted(by.get("release-note", []), key=lambda e: e.get("created_at", ""))
    if releases:
        latest = releases[-1]
        checked = {e["id"] for e in entries if latest["id"] in _out_edges(e, "verified-in", "invalidated-by")}
        stale_ud = [e for e in by.get("user-decision", [])
                    if (e["metadata"].get("scope") in {"structural", "policy"} or "structural" in e.get("tags", []))
                    and e.get("created_at", "") < latest.get("created_at", "") and e["id"] not in checked]
        if stale_ud:
            out.append(_proposal(
                "stale", f"unverified-after:{latest['id']}", "medium",
                f"최신 릴리스 {latest['id']} 이후 재확인되지 않은 구조·정책 결정 {len(stale_ud)}건",
                "릴리스가 나왔지만 이 결정들이 여전히 유효한지 확인한 기록(verified-in/invalidated-by)이 없다.",
                "결정마다 현재 릴리스에서도 유효한지 확인하고 verified-in 또는 invalidated-by 를 남긴다.",
                [e["id"] for e in stale_ud] + [latest["id"]], count=len(stale_ud),
            ))

    # (c) 비슷한 UD 가 서로 연결되지 않음 → supersedes/refines 누락 후보
    uds = {e["id"]: _text_of(e) for e in by.get("user-decision", [])}
    if len(uds) >= 2:
        vectors = _vectors(uds)
        linked = {(e["id"], t) for e in by.get("user-decision", []) for t in _out_edges(e, "supersedes", "refines", "depends-on", "references")}
        linked |= {(b, a) for a, b in linked}
        created = {e["id"]: e.get("created_at", "") for e in by.get("user-decision", [])}
        modules = {e["id"]: e["metadata"].get("module") for e in by.get("user-decision", [])}
        pairs = []
        ids = sorted(uds)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if (a, b) in linked or modules[a] != modules[b]:
                    continue
                score = _cosine(vectors[a], vectors[b])
                if score >= 0.55:
                    old, new = sorted((a, b), key=lambda x: created[x])
                    pairs.append((new, old, score))
        if pairs:
            out.append(_proposal(
                "stale", "supersede-missing", "low",
                f"같은 모듈에서 서로 비슷한데 연결되지 않은 사용자 결정 {len(pairs)}쌍",
                "나중 결정이 이전 결정을 대체하거나 정교화했는데 relations 에 남아 있지 않을 수 있다. drift 가 보이지 않는다.",
                "각 쌍을 읽고 supersedes 또는 refines 를 기록한다. 실제로 독립된 결정이면 무시한다.",
                [x for p in pairs for x in p[:2]], pairs=[{"newer": n, "older": o, "similarity": round(s, 2)} for n, o, s in sorted(pairs, key=lambda p: -p[2])[:10]],
            ))

    # (d) 확신이 낮고 채택 기록이 없는 AD
    undecided = []
    for e in by.get("agent-decision", []):
        age = _days(e.get("created_at"), now)
        if age is None or age < stale_days:
            continue
        conf = e["metadata"].get("confidence")
        low = (isinstance(conf, (int, float)) and conf < 0.6) or str(conf).lower() in {"low", "낮음"}
        followed = any(e["id"] in _out_edges(u, "followed-by", "raised") or e["id"] in _out_edges(e, "followed-by") for u in by.get("user-decision", [])) or bool(_out_edges(e, "followed-by"))
        if low and not followed:
            undecided.append(e["id"])
    if undecided:
        out.append(_proposal(
            "stale", "low-confidence-ad", "low", f"확신이 낮고 사용자 채택/기각 기록이 없는 agent-decision {len(undecided)}건 ({stale_days}일 이상)",
            "에이전트가 낮은 확신으로 내린 판단이 검토 없이 남아 있다.", "사용자 결정(UD)으로 채택·기각을 남기거나 재검토한다.", undecided,
        ))
    return out


# ── 4. 기록 누락·품질 ───────────────────────────────────────────────────

def analyze_quality(entries: list[dict[str, Any]], *, now: dt.datetime, stale_days: int = 30) -> list[dict[str, Any]]:
    by = _by_type(entries)
    ids = Counter(str(e["id"]) for e in entries)
    known = set(ids)
    out: list[dict[str, Any]] = []

    dup = sorted(i for i, c in ids.items() if c > 1)
    if dup:
        out.append(_proposal("quality", "duplicate-ids", "high", f"중복 id {len(dup)}개", "같은 id 가 둘 이상이면 relations 가 어느 entry 를 가리키는지 모호하다.",
                             "한쪽의 id 를 새 번호로 바꾸고 이를 가리키는 relations 를 갱신한다.", dup))

    dangling = [(e["id"], r["target"]) for e in entries for r in e["relations"] if r.get("target") and r["target"] not in known]
    if dangling:
        out.append(_proposal("quality", "dangling-relations", "high", f"존재하지 않는 entry 를 가리키는 관계 {len(dangling)}건", "끊긴 edge 는 그래프 traversal 에서 조용히 사라진다.",
                             "대상 id 의 오타를 고치거나 entry 를 만든다. 삭제된 entry 라면 관계를 제거한다.", [a for a, _ in dangling], pairs=[{"from": a, "to": b} for a, b in dangling[:15]]))

    issues = by.get("issue-note", [])
    missing = [e["id"] for e in issues if not e["metadata"].get("status") or not e["metadata"].get("severity")]
    if missing:
        out.append(_proposal("quality", "issue-missing-fields", "medium", f"status 또는 severity 가 없는 issue-note {len(missing)}건", "필수 필드가 없으면 열린 이슈 집계와 우선순위가 틀어진다.",
                             "status(open/fixing/partially-resolved/resolved)와 severity(low/medium/high)를 채운다.", missing))
    bad_vocab = [e["id"] for e in issues if (e["metadata"].get("severity") and str(e["metadata"]["severity"]) not in SEVERITY_VOCAB)
                 or (e["metadata"].get("status") and str(e["metadata"]["status"]) not in STATUS_VOCAB)]
    if bad_vocab:
        values = Counter(str(e["metadata"].get("severity")) for e in issues if str(e["metadata"].get("severity")) not in SEVERITY_VOCAB | {"None"})
        out.append(_proposal("quality", "vocab-drift", "low", f"권장 어휘 밖의 severity/status 를 쓰는 issue {len(bad_vocab)}건", "같은 의미가 다른 단어로 갈라지면 집계가 분리된다.",
                             "severity 는 low/medium/high 로 통일한다(예: minor→low, major→high).", bad_vocab, severity_values=dict(values)))

    no_module = [e["id"] for e in issues if not e["metadata"].get("module")]
    if len(no_module) >= 5:
        out.append(_proposal("quality", "module-missing", "low", f"module 이 없는 issue-note {len(no_module)}건 ({len(no_module) * 100 // max(len(issues), 1)}%)", "모듈이 없으면 모듈별 핫스팟과 workflow 개선 분석에서 빠진다.",
                             "metadata.module 을 채운다(저장소의 모듈·workflow 단위 이름과 맞춘다).", no_module))
    resolved_targets = {t for e in by.get("trouble-shooting", []) for t in _out_edges(e, "resolved-by")} | {e["id"] for e in issues if _out_edges(e, "resolved-by")}
    inconsistent = [e["id"] for e in issues if e["metadata"].get("status") == "resolved" and not _out_edges(e, "resolved-by")
                    and not any(e["id"] in _out_edges(t, "resolved-by") for t in by.get("trouble-shooting", []))]
    if inconsistent:
        out.append(_proposal("quality", "resolved-without-ts", "medium", f"resolved 인데 해결 TS 가 연결되지 않은 issue {len(inconsistent)}건", "어떻게 해결됐는지 근거가 그래프에 없다.",
                             "해결한 trouble-shooting 을 만들거나 기존 TS 에 resolved-by 로 연결한다.", inconsistent))
    stuck = []
    for e in issues:
        linked = e["id"] in resolved_targets or bool(_out_edges(e, "resolved-by"))
        if linked and e["metadata"].get("status") in {"open", "fixing"}:
            stuck.append(e["id"])
    if stuck:
        out.append(_proposal("quality", "open-but-resolved", "medium", f"해결 TS 가 연결됐는데 status 가 open/fixing 인 issue {len(stuck)}건", "TS 가 연결됐다면 issue 도 닫혔어야 한다. 집계에 유령 이슈가 남는다.",
                             "status 를 resolved 로 바꾸거나, 해결이 부분적이면 partially-resolved 로 바꾼다.", stuck))
    aged = [e["id"] for e in issues if e["metadata"].get("status") == "open" and (_days(e.get("created_at"), now) or 0) >= stale_days * 2 and not _out_edges(e, "resolved-by")
            and e["id"] not in resolved_targets]
    if aged:
        out.append(_proposal("quality", "aged-open", "low", f"{stale_days * 2}일 넘게 열려 있고 진행 기록이 없는 issue {len(aged)}건", "방치된 issue 는 신뢰를 떨어뜨린다.",
                             "여전히 유효하면 우선순위를 정하고, 아니면 닫는다.", aged))

    ts_missing = [e["id"] for e in by.get("trouble-shooting", []) if not e["metadata"].get("root_cause") or not e["metadata"].get("fix_summary")]
    if ts_missing:
        out.append(_proposal("quality", "ts-missing-fields", "medium", f"root_cause 또는 fix_summary 가 없는 trouble-shooting {len(ts_missing)}건", "원인이 빠진 TS 는 재발 분석과 승격(EP/PT)의 근거가 되지 못한다.",
                             "root_cause 와 fix_summary 를 채운다.", ts_missing))
    ts_unlinked = [e["id"] for e in by.get("trouble-shooting", []) if not _out_edges(e, "resolved-by", "caused-by", "references")
                   and not any(e["id"] in _out_edges(i, "resolved-by") for i in issues)]
    if ts_unlinked:
        out.append(_proposal("quality", "ts-without-issue", "low", f"어느 issue 와도 연결되지 않은 trouble-shooting {len(ts_unlinked)}건", "TS 는 보통 IN 으로 시작한다. 연결이 없으면 사건 추적이 끊긴다.",
                             "해당 issue-note 에 resolved-by 로 연결한다. issue 가 없었다면 사후 IN 을 만든다.", ts_unlinked))

    ad_missing = [e["id"] for e in by.get("agent-decision", []) if not all(e["metadata"].get(k) not in (None, "", []) for k in ("rationale", "alternatives", "confidence"))]
    if ad_missing:
        out.append(_proposal("quality", "ad-missing-fields", "medium", f"rationale/alternatives/confidence 가 비어 있는 agent-decision {len(ad_missing)}건", "AD 는 대안과 득실이 갈릴 때만 남기는 기록이다. 근거가 비면 AD 로서 가치가 없다.",
                             "빠진 필드를 채우거나, 대안이 없던 단순 작업이면 AD 가 아니라 worklog 로 옮긴다.", ad_missing))

    tag_groups: dict[str, Counter[str]] = defaultdict(Counter)
    for e in entries:
        for t in e.get("tags", []):
            tag_groups[_norm_tag(t)][t] += 1
    split = {k: v for k, v in tag_groups.items() if len(v) > 1}
    if split:
        out.append(_proposal("quality", "tag-drift", "low", f"표기만 다른 태그 {len(split)}묶음 (예: {', '.join(list(split.values())[0])})", "하이픈·밑줄·대소문자 차이로 같은 태그가 갈라져 검색과 군집이 분리된다.",
                             "태그 표기를 하나로 통일한다(소문자 kebab-case 권장).", [], groups={k: dict(v) for k, v in list(split.items())[:10]}))
    return out


# ── 실행·취합 ───────────────────────────────────────────────────────────

def stats(entries: list[dict[str, Any]], broken: list[str]) -> dict[str, Any]:
    by = _by_type(entries)
    open_issues = [e for e in by.get("issue-note", []) if e["metadata"].get("status") in {"open", "fixing", "partially-resolved"}]
    return {"entries": len(entries), "by_type": {k: len(v) for k, v in sorted(by.items())}, "open_issues": len(open_issues), "broken_lines": broken}


def rank(proposals: list[dict[str, Any]], max_per_kind: int | None = None) -> list[dict[str, Any]]:
    ordered = sorted(proposals, key=lambda p: (KINDS.index(p["kind"]), PRIORITY_ORDER[p["priority"]], -len(p["evidence"]), p["id"]))
    if not max_per_kind:
        return ordered
    seen: Counter[str] = Counter()
    kept = []
    for p in ordered:
        seen[p["kind"]] += 1
        if seen[p["kind"]] <= max_per_kind:
            kept.append(p)
    return kept


def render_markdown(report: dict[str, Any]) -> str:
    titles = {"promotion": "회고 승격 후보", "workflow": "workflow 개선안", "stale": "낡은 결정·교훈 점검", "quality": "기록 누락·품질"}
    s = report["stats"]
    lines = [f"# work-memory 분석 제안 ({report['generated_at'][:10]})", "",
             f"- 대상: `{report['workmem']}`  ·  entry {s['entries']}건  ·  열린 issue {s['open_issues']}건",
             f"- 제안 {len(report['proposals'])}건 — 결정적 분석{' + 모델 요약' if (report.get('draft') or {}).get('summary') else ''}. **work-memory 는 수정하지 않았다.**"]
    if s["broken_lines"]:
        lines.append(f"- 읽지 못한 줄 {len(s['broken_lines'])}건: {', '.join(s['broken_lines'][:5])}")
    draft = report.get("draft") or {}
    if draft.get("summary"):
        lines += ["", "## 요약", "", draft["summary"].strip()]
    rewrites = draft.get("proposals", {})
    for kind in KINDS:
        group = [p for p in report["proposals"] if p["kind"] == kind]
        if not group:
            continue
        lines += ["", f"## {titles[kind]} ({len(group)})"]
        for p in group:
            lines += ["", f"### [{p['priority']}] {p['title']}", ""]
            rewrite = (rewrites.get(p["id"]) or {}).get("rewrite")
            lines.append(rewrite.strip() if rewrite else p["why"])
            lines += ["", f"- 제안: {p['suggestion']}"]
            if p["evidence"]:
                shown = ", ".join(p["evidence"][:12]) + (f" 외 {len(p['evidence']) - 12}건" if len(p["evidence"]) > 12 else "")
                lines.append(f"- 근거: {shown}")
    return "\n".join(lines) + "\n"
