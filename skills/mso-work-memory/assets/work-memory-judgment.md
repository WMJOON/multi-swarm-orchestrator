<!--
드롭인 템플릿: 프로젝트의 상시 로드 rules(CLAUDE.md / AGENTS.md)에 아래 블록을 붙여넣는다.
SKILL.md "선제 기록 책임"은 always-on 강제를 프로젝트 rules 에 위임한다 — 이 스킬은
'어떻게'(CLI·스키마·넛지 훅)를 소유하고, 이 블록이 '언제'(판단 기준)를 상시 로드한다.
work-memory-check.sh 넛지가 알림을 띄우면, 이 기준으로 어떤 entry 를 남길지 판단한다.
-->

## Work-Memory 기록 책임 (always-on)

기록은 사용자가 요청할 때까지 기다리지 않는다. **향후 작업·구조에 지속 영향을 주는 결정·이슈·해결·통찰**을 에이전트가 스스로 판단해 `agent-context/work-memory/`에 먼저 남긴다. 단발성 지시·사소한 수정·단순 질문은 제외한다.

### track-record — 사건 단위 (파일/구조 변경에 수반)

| 타입 | 언제 남기나 | 필수 |
|---|---|---|
| **IN** issue-note | 문제를 **발견했거나 해결한 직후** — 끊을 틈 없이 같은 턴에 고쳤다면 IN을 회고로 남기고 TS와 함께 기록 | `metadata.severity`, `status` |
| **AD** agent-decision | 에이전트가 **권한 내에서 스스로 결정·실행**할 때 (고려한 대안은 metadata 에 기록) | `metadata.rationale`, `alternatives`, `confidence` |
| **AR** alternatives-record | 대안이 **둘 이상이고 득실이 갈려** 상위 권위(oracle = user 또는 metric)에 **옵션을 올려 판단받을** 때 (결정은 안 함) | `metadata.provided_by`, `options`, `recommended` |
| **UD** user-decision | 사용자가 방향·정책·구조를 명시적으로 결정할 때 (structural 태그 → repo-ADR / boundary → drift 추적) | `metadata.scope`, `boundary`, `criterion` |
| **TS** trouble-shooting | 문제를 해결·종결할 때 | `root_cause`, `fix_summary`, `resolved-by` 관계 |

> **IN/TS는 회고 기록이 정상이다.** UD는 *사용자 발화*라는 외부 트리거가 있어 자연히 인지되지만, IN/TS는 에이전트 내부 작업에서만 촉발돼 끊을 지점이 없다. 그래서 **아래 트리거 이벤트를 IN/TS 기록 앵커로 삼는다** — 이 순간을 지나쳤다면 IN+TS를 함께 회고로 남긴다:
>
> - 테스트가 red→green 으로 바뀐 직후
> - fix/revert 성격의 변경(버그·회귀·설정 오류 수정)을 검증한 직후
> - `fix:`/`revert:` 성격의 커밋을 만들기 직전
> - 시도가 막혀 접근을 바꾸기로 한 순간 (막힌 시도 = IN, 우회 = TS)
>
> "이미 고쳤으니 기록이 늦었다"는 누락 사유가 아니다. 늦은 IN+TS 쌍이 누락된 IN+TS보다 항상 낫다.

- 사용자가 채택할 **옵션 제시**는 AD 가 아니라 **AR** 로 남기고, 채택된 결정은 이어지는 UD 를 `followed-by`로 연결한다(AR→UD). AD 는 에이전트가 스스로 결정·실행한 경우에 쓴다.
- IN ↔ TS는 `resolved-by`/`caused-by`로 연결한다. 같은 턴에 함께 기록할 때도 두 entry를 모두 남기고 관계로 잇는다 (TS 단독 기록 금지 — 원인 추적이 끊긴다).

### insight-record — 추상화 그래디언트 (회고 흐름, 파일 변경과 무관)

track-record처럼 변경 즉시가 아니라 **사건이 일단락된 뒤 회고 시점**에 만든다.

| 타입 | 언제 남기나 |
|---|---|
| **EP** episode | TS로 사건이 일단락된 직후, 무슨 일이었는지 회고 (`analyzed-in`) |
| **PT** pattern | 비슷한 주제의 EP가 **여러 개 누적**되어 반복이 보일 때 (`generalized-in`) |
| **PR** principle | PT가 안정화되어 재사용 가능한 **원칙으로 응축**될 때 (`crystallized-in`) |

### worklog — workflow TTL node 실행 기록

`worklog` 는 세션 종료 요약이나 auditlog 요약이 아니다. workflow TTL 상의 `node -> node` 레일을 따라 수행한 작업을 기록한다. 작업에 대응되는 `workflow_id`/`node_id` 를 명시할 수 없으면 worklog 로 쓰지 않는다.

- workflow 레일 밖 작업을 수행했다면 먼저 **AD** 로 왜 레일 밖 판단을 했는지 남긴다.
- 레일 밖 상황이 문제/복구라면 **IN/TS** 로 원인과 해결을 남긴다.
- 반복되는 레일 밖 작업은 workflow TTL 갱신 후보로 환류한다.

> 절차·도구: entry 생성·검증·검색·그래프 traversal 은 `mso-work-memory` 의 `wm_node.py`.
> 자동 넛지: `work-memory-check.sh` 가 SessionStart(compact/resume)에서 위 판단을 상기시킨다. Stop은 worklog를 자동 생성하지 않으며, reminder 출력은 provider별 stdout 의미론 차이와 사용자 잡음을 피하기 위해 사용하지 않는다. 훅 넛지는 백스톱이고, 주 레버는 이 always-on 텍스트다.
