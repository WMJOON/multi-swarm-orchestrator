# modules_index

## Core Modules (Phase 기반)

| module | phase | purpose |
|---|---|---|
| module.model-decision.md | Phase 2 | Training Level 결정 3-Signal 판단 상세 |
| module.training-level.md | Phase 3 | TL-10/20/30 실행 흐름 상세 |

## Operational Modules (반복 최적화)

| module | purpose | 호출 관계 |
|---|---|---|
| module.model-retraining.md | data drift 감지 + 재학습 루프 + regression guard | Phase 1~5 재진입 |
| module.rollback.md | Degradation 정책 + Fallback 전략 + 모니터링 | ← mso-observability |

## Schemas

| schema | purpose |
|---|---|
| schemas/deploy_spec.schema.json | 모델 배포 계약 스키마 (reproducibility + evaluation + rollback) |
| schemas/handoff_payload.schema.json | workflow-optimizer → model-optimizer Tier Escalation Handoff |
| schemas/smart_tool_manifest.schema.json | Smart Tool manifest.json 표준 구조 |
