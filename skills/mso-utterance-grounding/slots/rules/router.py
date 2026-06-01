"""
rules slot — trigger_keywords 기반 Lv10 라우터.
mso-intent-registry.list_intents() 결과를 keywords.json으로 캐싱해 사용.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# registry lookup 경로 주입
_REGISTRY_SRC = Path(__file__).parent.parent.parent.parent / \
    "mso-intent-registry" / "src"
if str(_REGISTRY_SRC) not in sys.path:
    sys.path.insert(0, str(_REGISTRY_SRC))

_KEYWORDS_JSON = Path(__file__).parent / "keywords.json"


# ─── keywords.json 캐시 빌드 ─────────────────────────────────

def build_keywords_cache() -> dict[str, list[str]]:
    """
    registry에서 list_intents() 호출 → keywords.json 생성.
    intent_matrix priority 내림차순 정렬 (높은 priority = 먼저 매칭).
    """
    from lookup import list_intents, list_matrix_cells  # type: ignore

    cells = {c["intent_id"]: c.get("priority") or 99
             for c in list_matrix_cells(status="filled")}
    intents = sorted(list_intents(),
                     key=lambda i: cells.get(i["intent_id"], 99))
    mapping = {i["intent_id"]: i["trigger_keywords"] for i in intents
               if i["trigger_keywords"]}
    _KEYWORDS_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=2))
    return mapping


def _load_keywords() -> dict[str, list[str]]:
    if not _KEYWORDS_JSON.exists():
        return build_keywords_cache()
    return json.loads(_KEYWORDS_JSON.read_text())


# ─── 매칭 ────────────────────────────────────────────────────

def route(utterance: str,
          keywords: dict[str, list[str]] | None = None
          ) -> tuple[str | None, float]:
    """
    utterance에서 trigger_keywords 매칭.
    Returns: (intent_id | None, confidence)
      - matched  → (intent_id, 1.0)
      - unmatched → (None, 0.0)  → inference slot으로
    충돌 시 keywords.json 순서(priority 내림차순) 우선.
    """
    if keywords is None:
        keywords = _load_keywords()
    utt_lower = utterance.lower()
    for intent_id, kws in keywords.items():
        if any(kw in utt_lower for kw in kws):
            return intent_id, 1.0
    return None, 0.0


def refresh_cache() -> dict[str, list[str]]:
    """registry 변경 시 keywords.json 재생성."""
    return build_keywords_cache()
