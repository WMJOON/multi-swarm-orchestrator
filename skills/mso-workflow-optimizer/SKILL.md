---
name: mso-workflow-optimizer
metadata:
  version: "0.8.0"
description: >
  MSO workflow TTL ABox를 실행 가능한 LangGraph artifact로 컴파일하는 optimizer 스킬.
  TTL을 SSOT로 유지하면서 Vertex별 instruction, work-memory ContextPack,
  control_plane_events, memory_writeback_queue, provider routing을 포함한 generated/langgraph/workflow-id/graph.py,
  workflow_ir.json, optimizer_policy.json을 생성한다. 다음 상황에서 사용한다:
  (1) workflow/*.abox.ttl을 LangGraph 로컬 실행 그래프로 변환,
  (2) 비용/속도/품질/프라이버시 정책에 따라 node별 provider routing 계획 생성,
  (3) Ollama/local LLM, OpenAI API, Codex ChatGPT sign-in/access-token 같은 provider adapter
      선택을 TTL 밖 정책 파일로 분리,
  (4) Claude Code/Codex 같은 client agent를 control plane, LangGraph를 execution plane으로 분리,
  (5) HITL/HITLFE/HOTL/HOOTL judge semantics를 conditional edge/gate로 보존,
  (6) coding agent reasoning 비용을 줄이기 위해 반복 workflow를 local graph runtime으로 내리는 작업.
---

# MSO Workflow Optimizer

MSO workflow optimizer는 **TTL ABox를 읽는 compiler/runtime adapter**다. TTL은 계속 SSOT이고, LangGraph 코드는 `generated/` 아래 재생성 가능한 산출물이다.

```text
workflow/*.abox.ttl  ->  optimizer IR  ->  generated/langgraph/workflow-id/graph.py
        SSOT                 transient                 generated artifact
```

## 원칙

- TTL ABox를 직접 실행 정본으로 둔다. 생성된 LangGraph 코드는 수동 편집하지 않는다.
- workflow node의 `wf:instruction`은 Vertex instruction이고, work-memory는 Vertex별 ContextPack으로 주입한다.
- ContextPack 스코어링/선택 로직의 정본은 **mso-work-memory 의 `wm_context.py`** 다 (v0.7.0). `compile_workflow.py` 는 이를 로드해 위임한다 — sibling `skills/` 디렉토리 우선, `~/.claude/skills/` fallback. 따라서 이 스킬은 mso-work-memory 가 해석 가능한 환경을 전제한다.
- secret/API key/OAuth token은 TTL에 넣지 않는다. provider 선택은 정책 파일에 이름으로만 남긴다.
- `cost | speed | quality | privacy` 실행 모드를 정책으로 받아 node별 provider를 고른다.
- LangGraph 미설치 환경에서도 생성물 import와 fallback `invoke()`가 동작해야 한다.
- `HITL`, `HITLFE`, `HOTL`, `HOOTL` decision은 graph 조건부 edge/gate로 보존한다.
- **v0.7 Rail/Stream workflow를 그대로 컴파일한다.** 제어 흐름 추출은 **`mso-workflow-design`의 `wf_v07.control_graph`(>=0.13.0)가 정본**이고, 이 스킬은 그 결과에 실행 정책(judge→provider)만 입힌다. sibling `skills/` 우선, `~/.claude/skills/` fallback이며 design 스킬이 없으면 컴파일이 중단된다. 제어 Rail은 `default`·`escalates_to`뿐이고 `reads`·`delegates_to`·oracle Rail은 건너뛰며 경고로 남긴다. `wf:hasSubject`를 judge로 옮긴다(human=HITL, model·self·workflow=HOTL, system=HOOTL). `hasSubject=workflow`(하위 workflow)는 펼치지 않고 단일 노드로 둔다. v0.6(Project/Phase/Step) 어휘도 계속 지원한다. v0.7인데 읽을 수 없는 rail(없는 노드 참조)·출구 없는 decision은 조용히 넘기지 않고 오류로 중단한다.
- `hasSubject=human` 노드는 `requires_human`이다. `decisions[node]` 또는 `node_results[node]` 없이는 execution plane이 `awaiting_human:<node>`로 halt하며 자동 승인하지 않는다. halt 상태에서는 조건부 edge가 END로 간다.
- 되돌림 루프는 정책 `loop_limit`(기본 5)를 넘으면 `loop_limit:<node>`로 halt한다.
- **로컬 AI 서빙 엔진**: `ollama | vllm | sglang | lmstudio | omlx`(모두 OpenAI 호환 `/v1`). 일반 local 슬롯의 엔진은 정책 `local_engine` 또는 `--local-engine`으로 고르고, 엔드포인트는 정책 `engines.<name>.base_url`로 덮어쓴다(기본 포트: ollama 11434, vllm 8000, sglang 30000, lmstudio 1234, omlx 8000). 생성된 `graph.py`의 `engine_for(node_id)`가 노드의 엔진 설정을 돌려준다. API key는 TTL·정책에 넣지 않는다.
- Claude Code/Codex 같은 client agent는 **control plane**, LangGraph는 **execution plane**이다.
- execution plane은 기본적으로 `user-decision`을 직접 기록하지 않는다. human/metric oracle 확정은 control plane 책임이다.
- execution plane은 `alternatives-record` 후보나 `control_plane_event`를 만들어 workflow를 중단하고 control plane에 결정을 요청할 수 있다.
- work-memory 기록은 직접 쓰지 않는다. Vertex 실행 결과가 제출한 후보만 `memory_writeback_queue`에 `proposed` 상태로 쌓는다.

## Quick Start

```bash
python scripts/compile_workflow.py workflow/my-flow.abox.ttl \
  --out generated/langgraph \
  --workmem agent-context/work-memory \
  --policy optimizer-policy.yaml
```

생성물:

- `graph.py`: LangGraph가 있으면 `StateGraph`를 compile하고, 없으면 deterministic fallback graph를 제공한다.
- `workflow_ir.json`: TTL에서 추출한 phase/node/edge/provider routing IR.
- `context_packs`: node별 work-memory snapshot. 없거나 오래된 경우 런타임에서 `context_overrides`로 교체 가능 — 교체용 pack 은 `wm_context.py node --node <id> --ttl <abox> --json` 으로 동일 스코어링에서 재생성한다 (`context_overrides` 와 상보).
- `optimizer_policy.json`: 적용된 provider 선택 정책.
- `manifest.json`: 입력 TTL 해시, 생성 시각, artifact 경로.

정책 파일이 없으면 `cost` 모드 기본값을 쓴다.

```yaml
mode: cost
providers:
  default: local-ollama
  phase: python
  step: local-ollama
  validation: python
  decision:
    HITL: human
    HITLFE: codex-chatgpt
    HOTL: local-ollama
    HOOTL: local-ollama
context:
  enabled: true
  mode: snapshot
  top_k: 5
  relation_depth: 1
  include_types: [principle, pattern, episode, user-decision, agent-decision, alternatives-record, issue-note, trouble-shooting]
writeback:
  enabled: true
  mode: queue-only
  allowed_types: [issue-note, agent-decision, alternatives-record, trouble-shooting]
  requires_review: true
planes:
  control_plane_agents: [claude-code, codex]
  execution_plane: langgraph
governance:
  user_decision:
    execution_plane: forbidden
    control_plane: record-after-human-or-metric-oracle
  alternatives_record:
    execution_plane: queue-or-interrupt
    control_plane: present-to-user-or-metric-oracle
  control_plane_events:
    enabled: true
    halt_on: [request_user_decision, propose_alternatives]
```

## 작업 절차

1. `mso-workflow-design`으로 workflow TTL ABox가 최신인지 먼저 확인한다.
2. `scripts/compile_workflow.py`로 LangGraph artifact를 생성한다.
3. `workflow_ir.json`에서 node order, edge, provider routing, `context_packs`를 검토한다.
4. 실제 실행 runner가 필요한 경우 generated `graph.py`의 `_run_node` adapter 경계에서 provider별 실행 함수를 감싼다.
5. 실행 중 `control_plane_events`가 생기면 workflow를 멈추고 Claude Code/Codex 같은 control plane에서 사용자 또는 metric oracle 결정을 처리한다.
6. 실행 후 `memory_writeback_queue`를 검토해 AD/AR/IN/TS 후보만 work-memory에 승격한다. UD는 human/metric oracle 이후 별도 기록한다.

## References

- [references/langgraph-adapter.md](references/langgraph-adapter.md): IR, provider policy, generated graph 계약.
