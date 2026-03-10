---
id: dir-001
type: framework
name: MECE Decomposition
domain: analysis
taxonomy_path: [analysis, decomposition]
concepts: [mutually_exclusive, collectively_exhaustive]
applicable_vertex_types: [agent]
applicable_motifs: [fork_join, diamond]
related: [dir-002]
---

# MECE Decomposition

문제를 **상호 배타적(Mutually Exclusive)이고 전체 포괄적(Collectively Exhaustive)인** 단위로 분해한다.

## 적용 절차

1. 전체 범위를 정의한다
2. 1차 분해 축을 선택한다 (시간/기능/고객 등)
3. 각 범주가 겹치지 않는지 확인한다 (ME)
4. 누락된 범주가 없는지 확인한다 (CE)
5. 2차 분해가 필요하면 재귀 적용한다

## 판단 기준

- 분해 결과의 합이 원래 범위를 복원하는가?
- 각 범주에 독립적으로 작업을 할당할 수 있는가?

## 주의

- 축이 불명확하면 "기타" 범주가 비대해진다 → 축 재선택
- 3단계 이상 깊이는 실행 복잡도 대비 효용이 감소한다
