---
name: mso-mental-model-design
description: |
  Topology를 읽어 실행 가능한 mental_model_bundle을 생성한다.
  Use when nodes need domain-specific interpretation and checkpoint rules.
disable-model-invocation: true
---

# mso-mental-model-design

> 목표 토폴로지만 있으면 기본 멘탈 모델 번들을 자동 생성한다.

---

## 실행 프로세스

### Phase 1) 토폴로지 입력 확인
- `workflow_topology_spec`에서 run_id, nodes를 읽는다.
- 노드가 없으면 실패.

### Phase 2) 차트 생성
- 각 node마다 1개 이상의 `local_chart`를 생성한다.
- chart_id는 `chart_<node_id>_<idx>` 패턴.

### Phase 3) 번들 작성
- `node_chart_map`을 구성해 topology node와 chart를 대응.
- output_contract, execution_checkpoints를 채운다.

### Phase 4) 산출물 저장
- `workspace/.mso-context/active/<Run ID>/20_mental-model/mental_model_bundle.json`에 기록.

### when_unsure
- 입력 도메인이 추상적인 경우 `General` 도메인으로 fallback하고 assumptions 필드에 근거 기재.

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|---|---|---|
| → | `mso-execution-design` | 실행계획 생성의 입력 |
| ← | `mso-workflow-topology-design` | topology spec를 소비 |

---

## Scripts

- `python3 scripts/build_bundle.py --topology workspace/.mso-context/active/<Run ID>/10_topology/workflow_topology_spec.json --output workspace/.mso-context/active/<Run ID>/20_mental-model/mental_model_bundle.json`
