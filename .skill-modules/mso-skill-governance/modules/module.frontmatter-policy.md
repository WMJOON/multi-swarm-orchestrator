# module.frontmatter-policy

## 검사 항목

- `core.md`, `modules/modules_index.md`, `references/source_map.md` 존재
- `SKILL.md` frontmatter가 비어있지 않은지
- `scripts/` 디렉토리 존재 여부(실행형 스킬은 필수)

## 규칙

- 미준수는 `warn` 또는 `fail`로 기록
- 경고는 `governance_report.md`에 보류 사유로 남김
