"""
script slot — IntentTurn turns.jsonl append.
MSO_TURNS_PATH 환경변수로 경로 오버라이드 가능 (테스트용).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_TURNS_PATH = Path("workspace/.mso-context/conversation/turns.jsonl")

SCHEMA_HEADER = {
    "type": "schema",
    "version": "0.1.0",
    "intent_schema": "nlu_intent/0.1.0",
}


def _turns_path() -> Path:
    env = os.environ.get("MSO_TURNS_PATH")
    return Path(env) if env else _DEFAULT_TURNS_PATH


def _ensure_file(path: Path) -> None:
    """파일 없으면 schema 헤더 행 포함해 초기화."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        header = dict(SCHEMA_HEADER)
        header["created_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(header, ensure_ascii=False) + "\n")


def new_turn_id() -> str:
    """UUID4 기반 turn ID (ULID 대용)."""
    return str(uuid.uuid4())


def append_turn(
    turn_id: str,
    session_id: str,
    utterance: str,
    grounded: dict,
    prev_turn_id: str | None,
    duration_ms: int,
) -> None:
    """
    IntentTurn 레코드를 turns.jsonl에 append.
    grounded: GroundedCommand dict
    """
    path = _turns_path()
    _ensure_file(path)

    record = {
        "type":                         "turn",
        "turn_id":                      turn_id,
        "session_id":                   session_id,
        "timestamp":                    datetime.now(timezone.utc).isoformat(),
        "utterance":                    utterance,
        "resolved_intent_id":           grounded.get("intent_id"),
        "resolved_target_entity_id":    grounded.get("target_id"),
        "resolved_target_concepts":     grounded.get("target_concepts", []),
        "slots_filled":                 json.dumps(grounded.get("slots", {}),
                                                   ensure_ascii=False),
        "reprompt_count":               len(grounded.get("reprompt_slots", [])),
        "success":                      not grounded.get("reprompt_needed", False),
        "duration_ms":                  duration_ms,
        "prev_turn_id":                 prev_turn_id,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
