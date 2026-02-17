# module.ticket-adapter

## Mapping
- `tags` → `role`: review/worker inference
  - `review` tag -> `reviewer`
  - `worker` default
- `priority` high/critical -> `timeout_seconds` 상향
- `dependencies` -> `depends_on`

## Output
`handoff_payload` fields:
- `run_id`
- `task_id`
- `owner_agent`
- `role`
- `objective`
- `allowed_paths`
