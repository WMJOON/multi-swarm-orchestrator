# references

- `ticket.schema.json` 호환: `id`, `status`, `created`, `dependencies`, `owner`, `due_by`
  (`skills/mso-task-context-management/schemas/ticket.schema.json`)
- AAOS 고정 필드는 제거하고 범용 필드(`task_context_id`, `state`, `owner`, `due_by`, `dependencies`)만 사용
- Audit/Observability는 downstream에서 frontmatter을 읽어 추적
