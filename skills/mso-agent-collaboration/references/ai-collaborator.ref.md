# ai-collaborator SoT reference

Canonical path (resolved at runtime):
- embedded baseline: `01.product/skills/mso-agent-collaboration/v0.0.1/Skill/ai-collaborator`
- 경로 override는 `01.product/config.yaml`의 `resolve_order` relative 항목을 통해서만 허용됩니다.

Used schemas:
- `task-handoff.schema.json`
- `output-report.schema.json`
- `run-manifest.schema.json`

Fallback policy:
- 기본적으로 내장본을 우선 사용.
- 번들 미사용 가능 상태면 fallback 결과만 반환.
