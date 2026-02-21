# ai-collaborator SoT reference

Canonical path (resolved at runtime):
- 외부 의존: `ai-collaborator`는 이 저장소에 포함되지 않으며, 별도 설치가 필요합니다.

Used schemas:
- `task-handoff.schema.json`
- `output-report.schema.json`
- `run-manifest.schema.json`

Fallback policy:
- `ai-collaborator` 미설치 시 fallback 결과만 반환하고, `requires_manual_confirmation=true`를 설정한다.
