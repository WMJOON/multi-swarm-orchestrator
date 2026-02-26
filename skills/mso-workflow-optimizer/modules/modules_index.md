# modules_index

## Core Modules (Phase 기반)

| module | phase | purpose |
|---|---|---|
| module.analysis-optimizing.md | Phase 1–5 | 5-Phase 전체 오케스트레이션 + operation-agent 에스컬레이션 루프 + drawio 노드 매핑 |
| module.agent-decision.md | Phase 2 | Automation Level 결정 3-Signal 판단 상세 |
| module.automation-level.md | Phase 3 | Level 10/20/30 실행 흐름 상세 |
| module.hitl-feedback.md | Phase 5 | HITL 피드백 수렴 및 goal 산출 상세 |

## Operational Modules (반복 최적화)

| module | purpose | 호출 관계 |
|---|---|---|
| module.process-optimizing.md | 프로세스 실행·분석·평가 반복을 통한 워크플로우 구조 개선 | → llm-as-a-judge를 서브프로세스로 호출 |
| module.llm-as-a-judge.md | LLM 기반 데이터 라벨링 + 정량 품질 검증 + HITL 규칙 개선 루프 | ← process-optimizing 또는 독립 실행 |
