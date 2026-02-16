---
name: mso-execution-design
description: |
  Map topology and mental model into execution plan, including node modes,
handoff contracts, and fallback rules.
disable-model-invocation: true
---

# mso-execution-design

## 실행 프로세스

### Phase 1) 입력 정합성
- topology와 bundle를 읽어 기본 키 존재 확인
- CC-01/CC-02에 필요한 mapping 기본 구조 확인

### Phase 2) 노드 매핑
- topology nodes → chart id 매핑 생성
- task-to-chart 역방향 매핑 생성

### Phase 3) 모드/모델 정책
- theta band 기반으로 mode 및 model 선호도 결정

### Phase 4) handoff/fallback
- 노드 출력/입력 키를 정의한 handoff_contract 산출
- 실패 시 fallback_rules를 기록

### when_unsure
- 모델 선택이 불명하면 `default`로 기록하고 근거를 note에 남긴다.

**산출물**: `outputs/execution_plan.json`

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | CC-01: topology_spec를 입력으로 소비 |
| ← | `mso-mental-model-design` | CC-02: mental_model_bundle를 입력으로 소비 |
| → | `mso-agent-audit-log` | 실행 결과를 audit log에 기록 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| 실행계획 생성 | `python3 scripts/build_plan.py --topology outputs/workflow_topology_spec.json --bundle outputs/mental_model_bundle.json --output outputs/execution_plan.json` |
| 출력 스키마 검증 | [schemas/execution_plan.schema.json](schemas/execution_plan.schema.json) |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
