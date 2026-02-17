# module.topology-selection

## Purpose
목표의 성격, 리스크 허용도, 의존 그래프 복잡도를 바탕으로 topology type을 선택한다.

## Rules
- `goal`이 단선형 규칙성/검증형인 경우: `linear`
- 조건 분기/케이스가 많은 경우: `fan_out`
- 다단 병합이 필요한 의존 수렴형: `fan_in`
- 재사용/반복 의사결정이 강하고 혼재된 경우: `dag`
- 루프 성격(정교화, 반복 개선)인 경우: `loop`

## Output
- 선택된 `topology_type`과 선택 근거를 SKILL 출력에 기록한다.
