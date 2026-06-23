# GroundedCommand — 계약 명세서

> **Governance 등록**: MSO v0.3.1 · 2026-05-27
> **상태**: ACTIVE
> **다음 검토**: v0.4.0 (Lv20 모델 통합 시)

---

## 개요

`GroundedCommand`는 자연어 운영 명령을 구조화된 실행 명세로 변환한 출력 계약이다.

| 항목 | 값 |
|------|---|
| **Producer** | `mso-intent-analytics` · `src/pipeline.py::ground()` |
| **Consumer** | `mso-orchestration` → intent_id 기반 Smart Tool 디스패치 |
| **Schema 소유** | `mso-intent-analytics/references/schemas/nlu_intent.yaml` |
| **버전** | 0.1.0 |
| **포맷** | JSON (dict) |

---

## 필드 명세

```jsonc
{
  // ── 의도 분류 ───────────────────────────────────────────
  "intent_id":        "dispatch_ticket",      // string|null  — 매칭된 intent (미분류=null)
  "confidence":       1.0,                    // float 0.0~1.0 — Lv10=1.0, Lv30=0.x, Lv20=0.x
  "tier":             "Lv10",                 // "Lv10"|"Lv30"|"Lv20" — 분류에 사용한 계층

  // ── 엔티티 해석 ─────────────────────────────────────────
  "target_id":        "ticket-217",           // string|null  — 엔티티 참조 ID
  "target_concepts":  ["TicketEvent","FailedTicket"],  // string[]  — SKOS 개념 목록

  // ── 슬롯 ────────────────────────────────────────────────
  "slots": {                                  // object  — SlotSpec에 따라 채워진 값
    "ticket_ref": "ticket-217",
    "reason":     "manual_retry"
  },

  // ── 재발화 요청 ──────────────────────────────────────────
  "reprompt_needed":  false,                  // boolean  — required 슬롯 미충족 시 true
  "reprompt_slots":   [],                     // string[]  — 미충족 슬롯 이름 목록

  // ── 세션·턴 추적 ─────────────────────────────────────────
  "session_id":       "run-abc:op1:001",      // string  — SessionContext.session_id
  "turn_id":          "550e8400-e29b-41d4..."  // string  — UUID4 (IntentTurn PK)
}
```

### 필드 상세

| 필드 | 타입 | nullable | 설명 |
|------|------|----------|------|
| `intent_id` | string | ✓ | `mso-intent-analytics`에 등록된 intent ID. 미분류 발화 = `null`. |
| `confidence` | float | — | Lv10 keyword match = `1.0`. LLM/모델 신뢰도 = `0.0~1.0`. |
| `tier` | "Lv10"\|"Lv30"\|"Lv20" | — | 분류에 사용한 계층. Lv10이 최우선, Lv30(LLM) fallback, Lv20(경량 모델) 선택적. |
| `target_id` | string | ✓ | 슬롯에서 추출한 엔티티 참조. 예: `ticket-217`, `run-abc`. |
| `target_concepts` | string[] | — | RDF SKOS 개념 목록. 예: `["TicketEvent","FailedTicket"]`. 빈 배열 허용. |
| `slots` | object | — | fill_policy에 따라 채워진 슬롯 값 맵. 미충족 required 슬롯은 포함 안 됨. |
| `reprompt_needed` | boolean | — | `true`이면 Consumer는 `reprompt_slots`를 사용자에게 재확인 요청해야 한다. |
| `reprompt_slots` | string[] | — | 미충족 required 슬롯 이름 목록. `reprompt_needed=false`이면 빈 배열. |
| `session_id` | string | — | 연속 대화 세션 식별자. `run-NNN:op-NNN:seqNNN` 패턴 권장. |
| `turn_id` | string | — | UUID4. `turns.jsonl` IntentTurn 행의 PK. |

---

## Consumer 처리 규칙

```
if grounded["reprompt_needed"]:
    # 재발화 요청 — Smart Tool 미실행
    ask_user(grounded["reprompt_slots"])
elif grounded["intent_id"] is None:
    # 미분류 — turns.jsonl에 unresolved 기록 후 안내
    fallback_response()
else:
    # Smart Tool 디스패치
    smart_tool = TOOL_REGISTRY[grounded["intent_id"]]
    smart_tool.execute(grounded["slots"], grounded["target_id"])
```

---

## 생산 경로 (Producer) — §11 재편

```
자연어 utterance
    │
    ▼ [앞단] UUG  uug-grounding  ug ground "<발화>"   (repo 밖, 01_user-utterance-grounding)
  intent_id  (+ target_project)
    │
    ▼ [뒷단] mso-intent-analytics  src/pipeline.py::ground(utterance, intent_id)
    │   ├ normalize.py        (NFC, 공백 collapse — slot 추출 전처리)
    │   ├ slot_filler.py      slots_filled, reprompt_needed, reprompt_slots
    │   ├ resolver.py         target_id, target_concepts
    │   ├ validator.py        (SHACL or 직접 검사) conforms, violations
    │   └ turn_writer.py      turns.jsonl append
    ▼
  GroundedCommand 반환 (tier="UUG")
```

> §11: 앞단(utterance→intent 분류)은 UUG 흡수. 구 `mso-utterance-grounding` 의 rules/inference(Lv10 router / Lv30 LLM)는 제거됨 — intent 는 UUG 가 공급. 뒷단만 MSO(`mso-intent-analytics`).

---

## 버전 이력

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| 0.1.0 | 2026-05-27 | 초기 계약. MSO v0.3.1 M5 등록. |
| 0.2.0 | 2026-06-17 | §11 재편: Producer = mso-intent-analytics 뒷단 dispatch. 앞단(intent 분류)은 UUG. tier="UUG". |

---

## 관련 문서

- [mso-intent-analytics SKILL.md](../../skills/mso-intent-analytics/SKILL.md)
- [mso-intent-analytics/references/schemas/nlu_intent.yaml](../../skills/mso-intent-analytics/references/schemas/nlu_intent.yaml)
- [mso-orchestration SKILL.md](../../skills/mso-orchestration/SKILL.md)
- [SPEC: utterance-grounding](../../../planning/mso-v0.3.1-SPEC-utterance-grounding.md)
