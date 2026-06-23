# LangGraph Adapter Contract

`mso-workflow-optimizer`는 MSO workflow TTL ABox를 LangGraph 실행 artifact로 컴파일한다.

## Inputs

- `*.abox.ttl`: `wf: <https://mso.dev/ontology/workflow#>` vocabulary를 쓰는 workflow ABox.
- optional policy YAML/JSON: 실행 모드, provider routing, context/writeback 정책.
- optional `agent-context/work-memory`: Vertex별 ContextPack snapshot 생성에 쓰는 JSONL memory root.

## Plane Model

- **Control plane**: Claude Code, Codex 같은 client agent. 사용자/metric oracle과 상호작용하고 `user-decision`을 확정 기록한다.
- **Execution plane**: LangGraph generated runtime. Vertex를 실행하고 state를 갱신한다.

기본 정책에서 execution plane은 `user-decision`을 직접 기록하지 않는다. 대신 `control_plane_events`에 `request_user_decision` 또는 `propose_alternatives`를 추가해 workflow를 멈추고 control plane에 넘긴다.

## IR

`workflow_ir.json`은 다음 필드를 가진다.

- `workflow_id`: project id 또는 TTL 파일명 기반 id.
- `source_ttl`: 입력 TTL 경로.
- `source_sha256`: 입력 TTL 내용 해시.
- `mode`: `cost`, `speed`, `quality`, `privacy` 중 하나.
- `nodes`: phase/step/decision/validation/group 노드 목록.
- `nodes[].instruction`: `wf:instruction`에서 온 Vertex instruction.
- `nodes[].context_selector`: node id/type/phase/judge/harness/instruction 기반 work-memory selector.
- `edges`: fixed edge와 decision branch edge 목록.
- `entrypoints`: incoming edge가 없는 시작 노드.
- `context_packs`: node id별 work-memory snapshot. 각 entry는 id/type/title/text/tags/metadata/relations/source_path/score를 포함한다.
- `writeback_policy`: generated graph가 `memory_writeback_queue`에 허용할 타입과 review 정책.
- `governance`: control plane / execution plane decision boundary.
- `warnings`: 순서 추론, branch target 누락 등 실행 전 검토 사항.

## Provider Policy

Provider는 실행 adapter 이름일 뿐이다. secret은 정책 파일에도 넣지 않는다.

- `local-ollama`: 비용/프라이버시 최적화용 local LLM adapter.
- `openai-api`: API key 기반 OpenAI adapter.
- `codex-chatgpt`: Codex/ChatGPT sign-in 또는 access-token 기반 adapter.
- `python`: deterministic script/harness adapter.
- `human`: HITL gate adapter.

## Generated Graph

생성된 `graph.py`는 다음 함수를 제공한다.

- `build_graph()`: LangGraph 설치 시 compiled graph, 미설치 시 fallback graph 반환.
- `invoke(initial_state=None)`: graph 실행 convenience wrapper.
- `node_specs()`: node metadata 반환.

LangGraph artifact는 generated output이다. 수동 변경하지 말고 TTL+policy에서 재생성한다.

## Runtime State Contract

Generated node는 다음 state channel을 읽고 쓴다.

- `active_context[node_id]`: 해당 Vertex에 공급된 ContextPack.
- `context_overrides[node_id]`: snapshot 대신 런타임 resolver가 공급한 ContextPack. 있으면 snapshot보다 우선한다.
- `node_outputs[node_id]`: planned/executed status, provider, instruction, context entry ids.
- `node_results[node_id].memory_writeback`: 실행 adapter가 제출하는 work-memory 후보.
- `node_results[node_id].control_plane_event`: execution plane이 control plane에 넘기는 event. 예: `propose_alternatives`.
- `control_plane_events`: Claude Code/Codex가 처리할 pending event queue.
- `halted` / `halt_reason`: control plane 개입이 필요해 execution plane 진행을 멈춘 상태.
- `memory_writeback_queue`: 직접 기록하지 않고 review가 필요한 후보를 누적하는 큐.

Writeback queue는 `queue-only`다. `user-decision`은 execution plane에서 거부하고 human/metric oracle 뒤 control plane에서 별도 기록한다. `alternatives-record`는 execution plane이 후보로 만들거나 `propose_alternatives` event로 올릴 수 있다.
