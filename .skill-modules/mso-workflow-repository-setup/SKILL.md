---
name: mso-workflow-repository-setup
description: |
  Workflow Repository Setup skill for MSO v0.2.2.
  Use when promoting workflow-design into a repository-level setup layer that defines workflow structure,
  scaffolding contracts, memory boundaries, repository layout, and harness setup inputs.
  Triggers: "workflow-repository-setup", "workflow repository", "workflow-design layer",
  "scaffolding-design", "workflow scaffold", "memory layer", "repository setup".
---

# mso-workflow-repository-setup

> 이 스킬은 기존 workflow-design layer를 repository-level setup layer로 승격한다.
> 목적은 실행 계획을 만드는 것이 아니라, workflow가 장기적으로 재사용·감사·최적화될 수 있는 repository 구조와 harness 입력 계약을 고정하는 것이다.

---

## 핵심 위치

```text
workflow-design + scaffolding-design
  -> mso-workflow-repository-setup
  -> mso-harness-setup
  -> mso-task-execution / audit-log / observability
```

`mso-execution-design`이 맡던 "실행 DAG 생성" 관점은 제거한다. v0.2.2에서는 workflow repository가 먼저 구조화되고, harness가 runtime event/policy/evaluation 계약을 생성한다.

---

## 책임 범위

### 이 스킬이 하는 일

- workflow repository layout 설계
- workflow-design 산출물과 scaffolding-design 산출물의 결합
- memory layer 경계 정의
- harness setup 입력 계약 생성
- governance/audit/optimizer가 읽을 repository metadata 정의
- workflow lifecycle 디렉토리와 artifact naming convention 정의

### 이 스킬이 하지 않는 일

- provider runtime 실행
- runtime event normalization
- policy evaluation
- audit DB 적재
- optimizer decision
- LLM/model selection

---

## Layer Model

### 1. workflow-design Layer

| Component | Required | Role |
|------|------|------|
| workflow-design | required | goal, task graph, workflow boundary, lifecycle state 정의 |
| scaffolding-design | required | repository layout, file contract, artifact slots, template binding 정의 |
| mental-model | optional | ontology, directive, domain semantics로 harness setup 보강 |

`mental-model`은 필수 설계 경로에서 제외한다. 필요할 때만 harness enrichment input으로 사용한다.

### 2. governance Layer

| Trigger | Target | Output |
|------|------|------|
| `SessionStart` | `mso-agent-audit-log` | 이전 세션 워크로그 3개 컨텍스트 주입 |
| `PreCompact` | `mso-agent-audit-log` | 컨텍스트 압축 직전 워크로그 기록 |
| `SessionEnd` | `mso-agent-audit-log` | 세션 종료 시 최종 워크로그 기록 |
| state-trigger from `audit-log.db` | optimizer layer | optimization signal |

> `Stop` hook은 deprecated. 루프 발생 및 기록 시점 부적합으로 `SessionEnd`로 대체.

### 3. optimizer Layer

Optimizer는 workflow repository metadata와 audit-log state trigger를 함께 읽는다.

| Input | Source |
|------|------|
| repository metadata | `workflow_repository.yaml` |
| runtime events | `audit-log.db` |
| state trigger | governance layer |
| stability signals | `mso-harness-setup` / `mso-observability` |

---

## 입력

| 입력 | 필수 | 설명 |
|------|------|------|
| workflow_design | 필수 | workflow objective, task graph, lifecycle state |
| scaffolding_design | 필수 | directory layout, required files, artifact templates |
| memory_requirements | 권장 | short-term, long-term, audit, retrieval memory 경계 |
| governance_hooks | 권장 | PreCompact, Stop, state-trigger 처리 규칙 |
| mental_model | 선택 | ontology/directive enrichment |

**when_unsure**: mental-model이 없으면 `optional_enrichment.pending`으로 표시하고 setup은 계속 진행한다.

---

## 실행 프로세스

### Phase 1: Workflow Boundary

1. workflow objective와 lifecycle state를 정의한다.
2. workflow repository의 scope를 정한다.
3. reusable workflow인지 project-local workflow인지 구분한다.

### Phase 2: Scaffolding Design

1. 필수 디렉토리와 artifact slot을 정의한다.
2. template binding 규칙을 정한다.
3. `workflow_repository.yaml` 초안을 만든다.

참조: [modules/module.scaffolding-design.md](modules/module.scaffolding-design.md)

### Phase 3: Memory Layer Design

1. runtime memory, audit memory, retrieval memory, optimizer memory를 분리한다.
2. memory owner와 write boundary를 지정한다.
3. audit-log와 optimizer state trigger 연결을 정의한다.

참조: [modules/module.memory-layer.md](modules/module.memory-layer.md)

### Phase 4: Harness Setup Contract

1. harness가 소비할 workflow metadata를 추출한다.
2. capability boundary와 lifecycle state를 넘긴다.
3. optional mental-model enrichment를 병합한다.
4. `mso-agent-audit-log` 환경 초기화를 실행한다 (DB + 훅 주입).

```bash
python3 ~/.skill-modules/mso-skills/mso-agent-audit-log/scripts/setup.py \
  --project-root {workspace_root} \
  [--worklog-dir {workspace_root}/00.agent_log/logs]
```

워크로그 디렉터리 생성, audit DB 초기화, 세션 훅 주입(멱등)을 한 번에 수행한다.

참조: [schemas/workflow_repository.schema.json](schemas/workflow_repository.schema.json)

---

## 산출물

| 산출물 | 경로 | 설명 |
|------|------|------|
| workflow_repository.yaml | `{output_dir}/workflow_repository.yaml` | workflow repository SoT |
| scaffolding_contract.md | `{output_dir}/scaffolding_contract.md` | directory/artifact/template 계약 |
| memory_layer.md | `{output_dir}/memory_layer.md` | memory owner/write/read boundary |
| harness_setup_input.yaml | `{output_dir}/harness_setup_input.yaml` | `mso-harness-setup` 입력 |
| audit 인프라 (`mso-agent-audit-log setup`) | `{workspace_root}/.mso-context/audit_global.db`, `.claude/settings.json` | DB + 워크로그 디렉터리 + 세션 훅 일괄 초기화 |

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | workflow-design 입력 제공 |
| ← | `mso-mental-model` | optional semantic enrichment |
| → | `mso-harness-setup` | repository metadata + scaffold + memory boundary 전달 |
| → | `mso-agent-audit-log` | governance hook snapshot/audit boundary 제공 |
| → | `mso-workflow-optimizer` | state-trigger와 repository metadata 제공 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| Workflow repository core | [core.md](core.md) |
| Workflow design module | [modules/module.workflow-design.md](modules/module.workflow-design.md) |
| Scaffolding design module | [modules/module.scaffolding-design.md](modules/module.scaffolding-design.md) |
| Memory layer module | [modules/module.memory-layer.md](modules/module.memory-layer.md) |
| Schema | [schemas/workflow_repository.schema.json](schemas/workflow_repository.schema.json) |
