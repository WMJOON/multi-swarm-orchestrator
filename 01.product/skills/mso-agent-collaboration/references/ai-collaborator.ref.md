# ai-collaborator SoT reference

Canonical path (resolved at runtime):
- embedded baseline: `01.product/skills/mso-agent-collaboration/v0.0.1/Skill/ai-collaborator`
- embedded-first 정책: 런타임은 내장 경로만 사용하며 외부 override를 탐색하지 않습니다.

Used schemas:
- `task-handoff.schema.json`
- `output-report.schema.json`
- `run-manifest.schema.json`

Fallback policy:
- 기본적으로 내장본을 우선 사용.
- 번들 미사용 가능 상태면 fallback 결과만 반환.
