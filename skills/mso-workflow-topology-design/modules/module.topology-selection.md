# module.topology-selection

## Purpose
목표의 성격, 리스크 허용도, 의존 그래프 복잡도를 바탕으로 topology type을 선택한다.

## Step 1: Motif 식별

선택 전 해당 워크플로우의 Motif 패턴을 먼저 파악한다.
→ Motif 정의·매핑·구분 기준: [module.motif-vocabulary.md](module.motif-vocabulary.md)

## Step 2: topology_type 선택 규칙

- `goal`이 단선형 규칙성/검증형인 경우: `linear` (Chain motif)
- 조건 분기/케이스가 많은 경우: `fan_out` (Star 또는 Switch motif)
- 다단 병합이 필요한 의존 수렴형: `fan_in` (Diamond motif)
- 재사용/반복 의사결정이 강하고 혼재된 경우: `dag`
- 루프 성격(정교화, 반복 개선)인 경우: `loop` (Loop motif)
- 병렬 처리 후 합류가 명확한 경우: `fan_out` + `fan_in` (Fork/Join motif)

## Output
- 선택된 `topology_type`, `motif` 이름, 선택 근거를 SKILL 출력에 기록한다.
