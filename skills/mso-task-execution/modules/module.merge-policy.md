# module.merge-policy

> v0.0.3: 머지 노드 정책 정의

## 적용 대상

`execution_graph`에서 `type: "merge"`인 노드에만 `merge_policy` 객체가 부여된다.

## strategy 유형

| strategy | 설명 | 사용 시나리오 |
|----------|------|--------------|
| `score_weighted` | 가중치 기반 종합 채점으로 최적 결과 선택 | 복수 브랜치 품질 비교 |
| `fast_forward` | 단일 브랜치만 존재하거나 충돌 없을 때 직접 병합 | 선형 합류 |
| `manual` | 자동 병합 불가, 사용자 리뷰 필수 | 고위험/전략 결정 |

## scoring_weights 검증

- `scoring_weights`는 key-value 객체이며, 모든 value의 합은 **1.0**이어야 한다.
- 기본 차원: `confidence`(0.4), `completeness`(0.3), `format_compliance`(0.3)
- 합계 ≠ 1.0인 경우 검증 실패(fail-fast)

## quorum 계산

- `quorum`: 병합에 필요한 최소 브랜치 결과 수
- 기본값: `max(2, len(parent_refs))`
- quorum 미달 시 병합 보류, `manual_review_required: true`로 에스컬레이션

## manual_review_required 에스컬레이션 조건

다음 조건 중 하나라도 해당되면 `manual_review_required: true`:
1. strategy가 `manual`
2. quorum 미달
3. 브랜치 간 결과 편차가 임계치 초과 (Critic/Judge Agent 판단)
4. HITL Gate(H1/H2) 조건 충족
