# mso-workflow-repository-setup Modules Index

| Module | Purpose | Status |
|------|------|------|
| [module.workflow-design.md](module.workflow-design.md) | workflow objective, boundary, lifecycle state 정의 | spec |
| [module.scaffolding-design.md](module.scaffolding-design.md) | repository layout, artifact slots, template binding 정의 | spec |
| [module.memory-layer.md](module.memory-layer.md) | runtime/audit/retrieval/optimizer memory boundary 정의 | spec |

---

## Loading Policy

1. Repository setup 요청이면 `SKILL.md`와 `core.md`를 먼저 읽는다.
2. workflow 구조 작업이면 `module.workflow-design.md`를 읽는다.
3. 디렉토리/템플릿 구조 작업이면 `module.scaffolding-design.md`를 읽는다.
4. memory/governance trigger 작업이면 `module.memory-layer.md`를 읽는다.
