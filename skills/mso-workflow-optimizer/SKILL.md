---
name: mso-workflow-optimizer
metadata:
  version: "0.6.5"
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
- secret/API key/OAuth token은 TTL에 넣지 않는다. provider 선택은 정책 파일에 이름으로만 남긴다.
- `cost | speed | quality | privacy` 실행 모드를 정책으로 받아 node별 provider를 고른다.
- LangGraph 미설치 환경에서도 생성물 import와 fallback `invoke()`가 동작해야 한다.
- `HITL`, `HITLFE`, `HOTL`, `HOOTL` decision은 graph 조건부 edge/gate로 보존한다.
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
- `context_packs`: node별 work-memory snapshot. 없거나 오래된 경우 런타임에서 `context_overrides`로 교체 가능.
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
