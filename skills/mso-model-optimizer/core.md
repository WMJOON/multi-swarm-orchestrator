# mso-model-optimizer — Core Rules

## Terminology

| 용어 | 정의 |
|------|------|
| Training Level (TL) | 학습 전략 깊이 (TL-10 / TL-20 / TL-30). 높을수록 학습 복잡도가 크다 |
| model-decision | 3-Signal을 종합하여 Training Level을 결정하는 판단 노드 |
| deploy_spec | 학습된 모델의 배포 계약. runtime, schema, rollback 전략을 포함 |
| Smart Tool | 자체 workflow를 가진 실행 모듈. manifest.json으로 구조를 선언 |
| inference slot | Smart Tool 내 `slots/inference/` 디렉토리. model artifact가 배치되는 위치 |
| model artifact | 학습 산출물. ONNX, PyTorch 모델 파일 또는 rules.json |
| rollback | 배포된 모델 성능 저하 시 LLM passthrough 또는 이전 버전으로 복귀하는 정책 |
| regression guard | 재학습된 모델이 기존 대비 개선되지 않으면 배포를 차단하는 안전장치 |
| data drift | 학습 시점과 추론 시점의 데이터 분포 차이 |
| rolling_f1 | 최근 N건의 inference 결과를 샘플링하여 계산한 이동 평균 F1 score |
| model-retraining | data drift 감지 시 재학습 루프를 실행하는 Operational Module |
| Handoff Payload | workflow-optimizer → model-optimizer 트리거 시 전달되는 JSON 구조체 |

---

## Input Interface

최소 입력:

- `tool_name` (string, required) — 대상 Smart Tool 식별자
- `inference_pattern` (string, required) — `classification | ner | ranking | tagging | extraction`
- `trigger_type` (string) — `"tier_escalation"` | `"direct"`
- 선택: `sample_io_ref`, `data_source[]`, `base_model`

**Handoff Payload (tier_escalation 트리거 시)**: [schemas/handoff_payload.schema.json](schemas/handoff_payload.schema.json) 참조. 인라인 예시는 SKILL.md Phase 0에 정의.

출력 경로 기본값:
- model artifact: `{workspace}/.mso-context/active/<run_id>/model-optimizer/tl{XX}_model/`
- eval report: `{workspace}/.mso-context/active/<run_id>/model-optimizer/tl{XX}_eval_report.md`
- deploy spec: `{workspace}/.mso-context/active/<run_id>/model-optimizer/deploy_spec.json`

---

## Output Interface

**decision_output** (Phase 2):

```json
{
  "training_level": "TL-20",
  "model_type": "classifier",
  "base_model": "distilbert-base-uncased",
  "rationale": ["Signal A: ...", "Signal B: ...", "Signal C: ..."],
  "escalation_needed": false
}
```

**deploy_spec** (Phase 5): [schemas/deploy_spec.schema.json](schemas/deploy_spec.schema.json) 참조. 인라인 예시는 SKILL.md Phase 5에 정의.

> `lifecycle_state`, `promotion_candidate`는 선택 필드. `cost_per_1k`는 `evaluation` 내 선택 필드.

---

## Processing Rules

1. Phase 0에서 `tool_name`과 `inference_pattern`을 반드시 확정한다.
2. Phase 1에서 데이터 소스 우선순위를 따른다: sample_io_ref > audit_global.db > workspace 로그 > 사용자 제공.
3. Phase 1의 `llm-as-a-judge` 서브프로세스 호출은 `mso-workflow-optimizer`의 인터페이스 계약을 따른다.
4. Phase 2 model-decision은 3-Signal(A: 데이터 가용성, B: 태스크 특성, C: 기존 모델 이력)로 TL을 결정한다.
5. Signal 충돌 시 보수적 TL(낮은 값) 선택 + `escalation_needed: true`.
6. Phase 3 실행 후 반드시 Phase 4 평가를 완료해야 Phase 5로 진행한다.
7. Phase 4에서 f1 기준 미달 시 Phase 5 진입 불가: Phase 2 회귀 또는 HITL 에스컬레이션.
8. Phase 5 HITL 타임아웃 시 배포 보류 + model artifact 보존.
9. 재학습된 모델은 **regression guard**: 기존 모델 대비 개선되지 않으면 배포하지 않는다.
10. deploy_spec.json의 `reproducibility` 블록은 필수: 재현성 없는 모델은 배포 불가.

---

## Error Handling

- `tool_name` 미제공: fail-fast.
- `inference_pattern` 미제공: fail-fast.
- 데이터 부족 (< 50건): TL-10 강제 선택 + warning 기록.
- TL-30 학습 실패: TL-20으로 강등 재시도, `carry_over_issues`에 기록.
- TL-20 학습 실패: TL-10으로 강등 재시도.
- TL-10도 실패: HITL 에스컬레이션 (데이터 품질 문제 가능성).
- eval.py 실행 실패: Phase 4 중단, fallback으로 수동 평가 안내.
- audit-log 기록 실패: 파이프라인 중단하지 않고 fallback 채널 안내.

---

## Security / Constraints

- `audit_global.db`는 읽기 전용으로 조회하며, 쓰기는 반드시 `mso-agent-audit-log` 스킬을 통한다.
- 학습 데이터에서 PII는 Phase 1에서 마스킹 처리 후 학습에 사용한다.
- model artifact 경로를 외부에 노출하지 않는다. deploy_spec을 통해서만 참조.
- 이전 버전 model artifact는 삭제하지 않는다 (rollback 가용성 보장).
- Handoff Payload의 API 키 등 민감 정보는 전달하지 않는다.

---

## when_unsure

- Signal 간 충돌(2개 이상): 보수적 TL + escalation_needed=true.
- `tool_name`이 모호하면: Smart Tool manifest가 있는 tool 목록을 제안하고 사용자 선택 요청.
- 데이터 품질 불확실: llm-as-a-judge를 samplingRatio=0.2로 실행 후 라벨 품질 확인, 불충분하면 HITL.
- 재학습 vs 신규 학습 구분 불가: `audit_global.db`에 이전 deploy_spec 존재 여부로 판단.
