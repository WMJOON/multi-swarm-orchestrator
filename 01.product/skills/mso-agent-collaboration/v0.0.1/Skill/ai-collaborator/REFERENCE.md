# CLI Reference (Unified ai-collaborator)

## Core Commands

### `run`

```bash
python3 scripts/collaborate.py run [OPTIONS]
```

Key options:
- `--provider/-p {codex|claude|gemini|antigravity}`
- `--message/-m <text>`
- `--tasks/-T "provider:prompt[:id]" ...`
- `--task-file <json|->`
- `--all`
- `--dir/-d <path>`
- `--context <file>`
- `--context-template "{context} ... {prompt}"`
- `--timeout/-t <seconds>`
- `--concurrency <n>`
- `--format/-f {text|json|json-map|jsonl}`
- `--output <file>`
- `--progress <jsonl>`
- `--resume`
- `--resume-failed`
- `--no-fail`
- `--strict-schema`

### `batch`

```bash
python3 scripts/collaborate.py batch <file|-> [OPTIONS]
```

Supports the same shared execution options as `run`.

### `status`

```bash
python3 scripts/collaborate.py status [--format json]
```

### `tokens`

```bash
python3 scripts/collaborate.py tokens [--format json]
```

## Swarm Commands

### `swarm init`

```bash
python3 scripts/collaborate.py swarm init --db <path>
```

### `swarm start`

```bash
python3 scripts/collaborate.py swarm start \
  --db <path> \
  --session <name> \
  --agents planner:claude,coder:codex,reviewer:antigravity
```

Options:
- `--poll-seconds <float>` (default: `2.0`)
- `--lease-seconds <int>` (default: `60`)
- `--max-attempts <int>` (default: `3`)
- `--inspect-interval <int>` (default: `2`)
- `--strict-schema`

### `swarm send`

```bash
python3 scripts/collaborate.py swarm send \
  --db <path> \
  --from <agent> \
  --to <agent> \
  --type TASK_REQUEST \
  --payload '{"goal":"..."}'
```

Options:
- `--trace-id <id>`
- `--thread-id <id>`
- `--strict-schema`

### `swarm inspect`

```bash
python3 scripts/collaborate.py swarm inspect --db <path> [--interval 2]
```

### `swarm stop`

```bash
python3 scripts/collaborate.py swarm stop --session <name>
```

## Environment Variables

- `ANTIGRAVITY_CMD_TEMPLATE` (required for `antigravity`)
- `CODEX_CMD_TEMPLATE` (optional override)
- `CLAUDE_CMD_TEMPLATE` (optional override)
- `GEMINI_CMD_TEMPLATE` (optional override)

Provider binary overrides:
- `CODEX_BIN`
- `CLAUDE_BIN`
- `GEMINI_BIN`
- `ANTIGRAVITY_BIN`

## Schemas

- `schemas/task-handoff.schema.json`
- `schemas/output-report.schema.json`
- `schemas/run-manifest.schema.json`
- `schemas/bus-message.schema.json`

Validation behavior:
- default: warn-and-continue
- strict: hard fail with `--strict-schema`
