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

### Phase 2) 차트 생성 + GT Angle 전파
- 각 node마다 1개 이상의 `local_chart`를 생성한다.
- chart_id는 `chart_<node_id>_<idx>` 패턴.
- topology 노드의 `theta_gt_band`, `theta_gt_range`, `semantic_entropy_expected`를 차트에 전파한다.
- **GT Angle Policy** (`--gt-policy`):

| 정책 | 동작 | 용도 |
|------|------|------|
| `inherit` | topology의 θ_GT를 그대로 사용 | 기본값. topology 설계를 신뢰할 때 |
| `widen` | band를 한 단계 넓힘 (narrow→moderate, moderate→wide) | 도메인 불확실성이 높거나 첫 반복일 때 |
| `override` | 차트 수준에서 직접 지정 | 도메인 전문가가 수동 조정할 때 |

### Phase 3) 번들 작성
- `node_chart_map`을 구성해 topology node와 chart를 대응.
- `gt_angle_config`에 적용된 정책을 기록한다.
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

- 기본 (topology θ_GT 상속):
  `python3 scripts/build_bundle.py --topology <topology_path> --output <output_path>`
- GT Angle 확대 (불확실 도메인):
  `python3 scripts/build_bundle.py --topology <topology_path> --gt-policy widen`
- GT Angle 수동 지정:
  `python3 scripts/build_bundle.py --topology <topology_path> --gt-policy override`
