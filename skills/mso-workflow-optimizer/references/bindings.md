# Bindings Contract

TTL은 **제어 구조의 정본**이고, 노드가 실제로 *무엇을 하는가*는 TTL에 없다(자연어 `wf:instruction`뿐).
그래서 컴파일 영역과 작성 영역을 나눈다.

| 영역 | 누가 | 산출 | 재생성 |
|---|---|---|---|
| 구조: 노드·엣지·분기·사람 게이트·루프 상한·컨텍스트 | 컴파일러(TTL에서) | `graph.py`, `workflow_ir.json` | 항상 가능, 손대지 않는다 |
| 본문: 각 노드가 실행할 것 | **AI 에이전트가 작성** | 대상 프로젝트의 `bindings.yaml` + 스크립트 | 프로젝트 소유, 스킬은 예시만 제공 |

스킬은 바인딩을 만들어 주지 않는다. `examples/bindings.example.yaml`은 형식 예시일 뿐이다.

## 에이전트 작성 절차

1. `compile_workflow.py <ttl> --print-ir`로 노드 id·type·judge·`instruction`을 읽는다.
2. 노드마다 종류를 정한다.
   - 결정적이고 반복 가능한 일 → `script` (스크립트는 프로젝트에 둔다)
   - 판단·생성·편집이 필요한 일 → `agent` (control plane 에 위임, 직접 LLM 을 부르지 않는다)
   - 사람 승인 → `interrupt`
3. `bindings.yaml`을 쓰고 `--bindings <file> --strict-bindings`로 컴파일한다. 오류는 모두 컴파일 시점에 난다.
4. 실행은 먼저 dry-run(`execute` 없음)으로 흐름을 확인한 뒤 `execute: true`로 돌린다.

## 종류별 계약

### `script`
| 키 | 의미 |
|---|---|
| `run` | argv 목록 또는 문자열(필수). 쉘을 거치지 않는다. |
| `cwd`, `timeout`, `env` | 작업 디렉터리(기본 `state.cwd`), 초(기본 600), 추가 환경변수 |
| `decision` | **decision 노드에서만, 그리고 필수.** `source: exit_code \| stdout_json`, `key`(stdout_json일 때), `map`(값 → TTL 분기 이름, `default` 가능) |

- 스크립트는 stdin으로 `{node_id, node_results, decisions, inputs}` JSON을 받는다. 환경변수 `MSO_WORKFLOW_ID`, `MSO_NODE_ID`가 설정된다.
- stdout이 JSON이면 `node_results[node].output`에 담긴다. 비-JSON이면 `stdout` 문자열로만 남는다.
- 비0 종료는 `script_failed:<node>`로 멈춘다(decision 노드는 `map`에 없는 값이면 `script_undecided:<node>`).
- **기본은 dry-run**이다. `state.execute`가 참일 때만 실행되고, 아니면 `node_outputs[node].status == "bound-dry-run"`이다.
- interrupt에서 재개해도 **이미 실행한 script는 다시 돌지 않는다**(`node_results[node].executed`). 그래도 script는 멱등하게 쓴다.

### `agent`
`node_results[node]`가 비어 있으면 `delegate_to_agent` 이벤트(`instruction`, `session`, `expects`)를 내보내고 `awaiting_agent:<node>`로 멈춘다.
control plane(Claude Code/Codex)이 작업한 뒤 결과를 `node_results[node]`에 넣거나 `resume()` 값으로 돌려준다.
작성자와 검증자를 분리해야 하면 검증 노드에 `session: fresh`를 쓴다.

### `interrupt`
사람 승인. 값 없이는 지나가지 않는다. 문자열(분기 이름) 또는 `{decision: ..., ...}`로 재개한다.

## 멈춤과 재개

- 체크포인터 없이(`invoke`): 멈춤은 `halted`/`halt_reason`이고, 이어가려면 값을 넣고 처음부터 다시 돌려야 한다.
- 체크포인터 있이(`start`/`resume`): 멈춤은 LangGraph `interrupt`이고 같은 지점에서 이어간다.

```python
import graph
saver = graph.sqlite_checkpointer("run.sqlite")        # pip install langgraph-checkpoint-sqlite
r = graph.start("run-1", {"execute": True, "cwd": "."}, saver)
r["__interrupt__"][0].value        # {"action", "reason", "node_id", ...}
r = graph.resume("run-1", "approved", saver)           # 사람 승인
r = graph.resume("run-1", {"summary": "..."}, saver)   # 에이전트 결과
```

**되돌림 루프 재진입**: 반려·게이트 실패로 이전 노드에 다시 들어오면, 그 노드가 *런타임에* 만든 결정·결과(script 실행, 재개 값)는 낡은 것으로 버리고 다시 받는다.
그래서 `design` 반려 뒤 `interpret`는 새 에이전트 결과를, `design`은 새 사람 결정을 기다린다. 초기 입력(`decisions`/`node_results`로 직접 준 값)은 유지된다.

멈춘 노드는 재개 시 처음부터 다시 실행되므로, 같은 노드 안에서 멈추기 전에 부작용을 두지 않는다.
`decision`이 비어 있으면 첫 분기로 가지 않고 `awaiting_decision:<node>`로 멈춘다.

## 컴파일 검증

| 상황 | 결과 |
|---|---|
| TTL에 없는 노드 키 | 오류 |
| `kind` 누락·알 수 없음 | 오류 |
| script에 `run` 없음, decision 노드에 `decision` 없음, `decision.map`이 분기에 없는 값 | 오류 |
| `decision`을 decision이 아닌 노드에 | 오류 |
| 바인딩 없는 노드 | 경고(`planned`로만 실행). `--strict-bindings`면 오류 |
| human 노드에 script | 경고(사람 게이트 우회) |

`manifest.json`에 `bindings`, `bindings_sha256`, `bound_nodes`가 기록된다.
