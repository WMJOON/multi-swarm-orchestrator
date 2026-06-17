"""
input_norm slot — utterance 정규화
Lv10: 결정론적. LLM 없음.
"""
from __future__ import annotations
import unicodedata


def normalize(utterance: str) -> str:
    """
    1. 앞뒤 공백 제거
    2. Unicode NFC 정규화 (한국어 자모 조합 안정화)
    3. 연속 공백 → 단일 공백
    """
    if not isinstance(utterance, str):
        raise TypeError(f"utterance must be str, got {type(utterance)}")
    text = unicodedata.normalize("NFC", utterance)
    text = " ".join(text.split())
    return text


def detect_language(utterance: str) -> str:
    """
    간단한 언어 감지 (로깅용, 라우팅 분기 없음).
    Returns: "ko" | "en" | "mixed"
    """
    ko_chars = sum(1 for c in utterance if "가" <= c <= "힣")
    en_chars = sum(1 for c in utterance if c.isascii() and c.isalpha())
    total = ko_chars + en_chars
    if total == 0:
        return "unknown"
    ko_ratio = ko_chars / total
    if ko_ratio >= 0.7:
        return "ko"
    if ko_ratio <= 0.3:
        return "en"
    return "mixed"
