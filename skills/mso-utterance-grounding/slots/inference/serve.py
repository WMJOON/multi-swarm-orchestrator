"""
inference slot — Lv30 LLM fallback / Lv20 경량 모델.
환경변수:
  GROUNDING_SKIP_LLM=1   → 테스트·오프라인 시 LLM 호출 건너뜀 (unresolved 반환)
  ANTHROPIC_API_KEY      → Lv30 LLM 호출에 사용
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_MODEL_DIR = Path(__file__).parent / "model"
_CONFIDENCE_THRESHOLD = 0.4


def classify(utterance: str,
             intents: list[dict],
             skip_llm: bool | None = None) -> tuple[str | None, float, str]:
    """
    utterance를 intent_id로 분류.
    Returns: (intent_id | None, confidence, tier)

    우선순위:
      1. Lv20 모델 아티팩트가 model/ 에 있으면 → _lv20_classify()
      2. skip_llm=True 또는 GROUNDING_SKIP_LLM=1 → (None, 0.0, "Lv30") 반환
      3. ANTHROPIC_API_KEY 있으면 → _lv30_llm_classify()
      4. 그 외 → (None, 0.0, "Lv30")
    """
    if skip_llm is None:
        skip_llm = os.environ.get("GROUNDING_SKIP_LLM", "0") == "1"

    meta_path = _MODEL_DIR / "meta.json"
    if meta_path.exists():
        return _lv20_classify(utterance, intents, meta_path)

    if skip_llm:
        return None, 0.0, "Lv30"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return _lv30_llm_classify(utterance, intents, api_key)

    return None, 0.0, "Lv30"


# ─── Lv30: LLM 호출 ──────────────────────────────────────────

def _lv30_llm_classify(utterance: str,
                       intents: list[dict],
                       api_key: str) -> tuple[str | None, float, str]:
    """
    Claude API로 intent 분류.
    단순 structured-output prompt — intent_id + confidence 반환.
    """
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None, 0.0, "Lv30"

    intent_list = "\n".join(
        f"- {i['intent_id']}: {', '.join(i.get('trigger_keywords', []))}"
        for i in intents
    )
    prompt = f"""다음 MSO 운영 명령 intent 목록에서 사용자 발화를 분류하세요.

Intent 목록:
{intent_list}

사용자 발화: "{utterance}"

가장 적합한 intent_id 하나와 신뢰도(0.0~1.0)를 JSON으로 반환하세요.
매칭되는 intent가 없으면 intent_id를 null로.
예시: {{"intent_id": "dispatch_ticket", "confidence": 0.92}}"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # JSON 파싱
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        result = json.loads(raw)
        intent_id = result.get("intent_id")
        confidence = float(result.get("confidence", 0.0))
        if confidence < _CONFIDENCE_THRESHOLD:
            intent_id = None
        return intent_id, confidence, "Lv30"
    except Exception:
        return None, 0.0, "Lv30"


# ─── Lv20: 로컬 모델 추론 ─────────────────────────────────────

def _lv20_classify(utterance: str,
                   intents: list[dict],
                   meta_path: Path) -> tuple[str | None, float, str]:
    """
    slots/inference/model/ 아티팩트 로드 후 추론.
    model-optimizer가 배치한 model.onnx + intent_labels.json 사용.
    """
    try:
        import onnxruntime as ort  # type: ignore
        import numpy as np         # type: ignore
        from tokenizers import Tokenizer  # type: ignore
    except ImportError:
        # Lv20 의존성 없으면 Lv30으로 fallback
        return None, 0.0, "Lv30"

    model_file = _MODEL_DIR / "model.onnx"
    tok_file   = _MODEL_DIR / "tokenizer.json"
    labels_file = _MODEL_DIR / "intent_labels.json"

    if not (model_file.exists() and tok_file.exists() and labels_file.exists()):
        return None, 0.0, "Lv30"

    labels: list[str] = json.loads(labels_file.read_text())
    tokenizer = Tokenizer.from_file(str(tok_file))
    sess = ort.InferenceSession(str(model_file))

    enc = tokenizer.encode(utterance)
    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)
    outputs = sess.run(None, {"input_ids": input_ids,
                               "attention_mask": attention_mask})
    logits = outputs[0][0]
    probs  = _softmax(logits)
    best   = int(np.argmax(probs))
    conf   = float(probs[best])

    intent_id = labels[best] if conf >= _CONFIDENCE_THRESHOLD else None
    return intent_id, conf, "Lv20"


def _softmax(x):
    import numpy as np
    e = np.exp(x - np.max(x))
    return e / e.sum()
