# Module: Scaffolding Design

## Goal

Scaffolding design은 workflow repository가 유지해야 할 파일 구조와 artifact slots를 정의한다.

---

## Default Layout

```text
workflow/
  workflow_repository.yaml
  README.md
  design/
    workflow-design.md
    scaffolding-contract.md
  memory/
    memory-layer.md
    retrieval-notes.md
  harness/
    harness_setup_input.yaml
    runtime-harness.override.yaml
  governance/
    hooks.yaml
    state-triggers.yaml
  optimizer/
    optimization-signals.yaml
    proposals/
  audit/
    README.md
```

---

## Artifact Slots

| Slot | Owner | Purpose |
|------|------|------|
| `design/` | workflow-repository-setup | workflow/scaffold contract |
| `memory/` | workflow-repository-setup + mental-model | curated memory boundary |
| `harness/` | harness-setup | runtime config inputs/overrides |
| `governance/` | skill-governance / audit-log | hooks and triggers |
| `optimizer/` | workflow-optimizer | proposals and state signals |
| `audit/` | agent-audit-log | local pointer, DB is external SoT |

---

## Template Binding

Templates must be explicit. Do not create hidden layout assumptions.

```yaml
templates:
  workflow_readme: templates/WORKFLOW_README.md
  memory_layer: templates/MEMORY_LAYER.md
  harness_input: templates/HARNESS_SETUP_INPUT.yaml
```
