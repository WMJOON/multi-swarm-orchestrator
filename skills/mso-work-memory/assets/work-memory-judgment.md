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
| **IN** issue-note | 문제를 발견한 즉시 (해결 전) | `metadata.severity`, `status` |
| **AD** agent-decision | 대안이 **둘 이상이고 득실이 갈리는** 판단을 내려 실행할 때 | `metadata.rationale`, `alternatives`, `confidence` |
| **UD** user-decision | 사용자가 방향·정책·구조를 명시적으로 결정할 때 (structural 태그 → repo-ADR) | `metadata.scope` |
| **TS** trouble-shooting | 문제를 해결·종결할 때 | `root_cause`, `fix_summary`, `resolved-by` 관계 |

- AD를 사용자가 채택하면, 이어지는 UD를 `followed-by`로 연결한다.
- IN ↔ TS는 `resolved-by`/`caused-by`로 연결한다.

### insight-record — 추상화 그래디언트 (회고 흐름, 파일 변경과 무관)

track-record처럼 변경 즉시가 아니라 **사건이 일단락된 뒤 회고 시점**에 만든다.

| 타입 | 언제 남기나 |
|---|---|
| **EP** episode | TS로 사건이 일단락된 직후, 무슨 일이었는지 회고 (`analyzed-in`) |
| **PT** pattern | 비슷한 주제의 EP가 **여러 개 누적**되어 반복이 보일 때 (`generalized-in`) |
| **PR** principle | PT가 안정화되어 재사용 가능한 **원칙으로 응축**될 때 (`crystallized-in`) |

> 절차·도구: entry 생성·검증·검색·그래프 traversal 은 `mso-work-memory` 의 `wm_node.py`.
> 자동 넛지: `work-memory-check.sh` 가 Stop/PreCompact 에서 위 판단을 상기시킨다.
