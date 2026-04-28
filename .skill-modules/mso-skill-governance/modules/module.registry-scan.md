# module.registry-scan

## 검사 항목

- 스킬 폴더 전체 스캔(`skills/*`)
- `core/modules/references/scripts` 필수 구성 충족율 체크
- 파일/디렉토리 과다(>10개 스킬)은 경고

## 규칙

- 필수 스킬 ID (10개):
  `mso-workflow-topology-design`, `mso-mental-model`, `mso-execution-design`,
  `mso-task-execution`, `mso-agent-collaboration`, `mso-agent-audit-log`,
  `mso-observability`, `mso-skill-governance`, `mso-workflow-optimizer`, `mso-model-optimizer`
- 누락이 1개 이상이면 fail
