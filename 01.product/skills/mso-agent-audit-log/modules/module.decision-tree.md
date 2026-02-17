# module.decision-tree

## 질문 축

- 의사결정 흔적을 어떻게 추적 가능한 트리로 남길 것인가?

## 규칙

- `decisions`는 사용자 승인/반려/반복 판단과 같은 핵심 분기에서 생성한다.
- `evidence`/`impacts`는 최소 1개 이상 링크 관계를 갖는 것을 권장한다.
- 단일 패턴에서 같은 `task_id`가 반복 발생하면 `transition_repeated=1`로 표시한다.
- 감시/관측 제안은 `decisions`로 직접 기록하지 않고 `notes`/`context`에 `decision_payload`를 요약해 둔다.
