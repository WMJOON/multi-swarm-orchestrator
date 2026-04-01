---
name: mso-task-execution
description: |
  Runtime execution orchestrator for MSO workflows.
  Consumes execution_graph.json and directive_binding.json to orchestrate skill calls in sequence,
  invoke runtime wrapper modules (OTel tracing, Guardrails validation), and record node snapshots.
  Use when an execution_graph needs to be run against actual skills/agents.
---

# mso-task-execution

> 이 스킬은 설계 산출물을 소비하여 실제 실행을 조율하는 **Runtime Orchestrator**다.
> 무엇을 어떤 순서로 실행할지 결정하고, wrapper module을 명시적으로 호출하며, 에러 발생 시 `mso-process-template`의 폴백 규칙을 참조하여 대응 행동을 트리거한다.

---

## 책임 레이어

### Orchestration Core (스킬 본체 책임)

- `execution_graph.json` + `directive_binding.json` 소비
- 노드 순서 및 의존성에 따라 스킬 호출
- 각 LLM 호출 전후 `wrapper.otel` 훅 호출 (before/after) `[spec-only, impl: v0.1.4]`
- pre-snapshot 단계에서 `wrapper.guardrails` 검증 호출 `[spec-only, impl: v0.1.4]`
- `mso-agent-audit-log`에 node_snapshot 적재

### Runtime Wrapper Modules (`_shared/` 하위, 스킬이 명시적으로 호출)

| 모듈 | 역할 | 상태 |
|------|------|------|
| `wrapper.otel` | LLM 호출 전후 OTel Span 생성·종료. 로컬 OTLP stdout 출력 (opt-in: Phoenix). trace_id를 Core에 반환, node_snapshots에 optional 저장 | spec-only |
| `wrapper.guardrails` | pre-snapshot JSON Schema 검증 + PII 스캔. 실패 시 auto-reprompt. v0.1.3: 자체 구현, v0.1.4+: 외부 SDK 교체 검토 | spec-only |

### retry/error routing — 정책 참조형

`mso-task-execution`은 에러 분류·severity·max_retry 값을 직접 정의하지 않는다.
**폴백 정책 정의는 `mso-process-template` 소유**이며, `mso-task-execution`은 이를 참조하여 실행 트리거만 담당한다.

| 단계 | 소유 | 내용 |
|------|------|------|
| 정책 정의 | `mso-process-template` | 에러 유형별 severity·action·max_retry |
| 실행 트리거 | `mso-task-execution` Core | 정책 조회 → retry 실행 / Sentinel 에스컬레이션 / checkout 복구 트리거 |

---

## 입력

| 파일 | 출처 | 필수 여부 |
|------|------|-----------|
| `execution_graph.json` | `mso-workflow-topology-design` (Phase A6) | 필수 |
| `directive_binding.json` | `mso-vertex-design` | 필수 |

**소비 전 검증:** `graph_id`, `schema_version`, `nodes[]` 필수 필드 존재 확인. `schema_version` 불일치 시 실행 중단.

---

## 실행 프로세스

### Phase 1: 입력 검증

1. `execution_graph.json` 필수 필드 확인 (`graph_id`, `schema_version`, `nodes[]`)
2. `directive_binding.json` 바인딩 완료 여부 확인 (`unbound_nodes[]` 존재 시 경고)
3. `schema_version` 일치 확인 (현재 `"1.0"`)

**when_unsure**: `unbound_nodes`가 있으면 경고 기록 후 실행 계속. 검증 실패는 즉시 중단.

### Phase 2: 노드 순서 결정

1. `nodes[]`의 `parent_refs`를 분석하여 위상 정렬(topological sort) 수행
2. 병렬 실행 가능 노드 그룹 식별 (공통 parent를 가진 branch 노드)
3. 실행 큐 구성

### Phase 3: 노드별 실행

각 노드에 대해 다음 순서로 실행:

```
1. wrapper.otel.before(node_id)          → span_context 반환  [spec-only]
2. directive_binding에서 해당 노드 directive 로드
3. bundle_ref의 스킬/에이전트 호출
4. wrapper.otel.after(span_context)      → trace_id 반환      [spec-only]
5. wrapper.guardrails.validate(output)   → pass / fail        [spec-only]
   - fail → auto-reprompt (max_retry 이내)
   - max_retry 초과 → hitl_block 에러 → Phase 4로
6. node_snapshot 구성 + mso-agent-audit-log 적재
```

### Phase 4: 에러 처리

1. 발생한 에러 유형을 `mso-process-template`의 폴백 규칙과 대조
2. action 결정: `retry` / `checkout` / `escalate`
3. `escalate` 시 → Sentinel Agent에 `hitl_request` 이벤트 전달

---

## 산출물

| 파일 | 경로 | 설명 |
|------|------|------|
| node_snapshots | `mso-agent-audit-log` DB | 각 노드 실행 결과 스냅샷 |
| execution_result.json | `{workspace}/.mso-context/active/<run_id>/30_execution/execution_result.json` | 전체 실행 요약 |

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | CC-01: execution_graph.json + topology_spec 소비 |
| ← | `mso-vertex-design` | CC-02: directive_binding.json 소비 |
| → | `mso-agent-audit-log` | CC-06: node_snapshots 적재 (trace_id optional 포함) |
| ↔ | `mso-process-template` | 폴백 규칙 참조 (정책 정의는 process-template 소유) |
| ← | `mso-skill-governance` | NHI 정책 위반 시 에스컬레이션 신호 수신 `[spec-only]` |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| 실행 계획 실행 | `python3 {mso-task-execution}/scripts/run_execution.py --graph <execution_graph.json> --binding <directive_binding.json>` |
| 출력 스키마 검증 | [schemas/execution_result.schema.json](schemas/execution_result.schema.json) |
| 상세 규칙 | [core.md](core.md) |
| Wrapper Modules 명세 | [modules/module.wrapper-otel.md](modules/module.wrapper-otel.md) `[spec-only]` |
| Wrapper Modules 명세 | [modules/module.wrapper-guardrails.md](modules/module.wrapper-guardrails.md) `[spec-only]` |
