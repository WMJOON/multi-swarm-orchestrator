# CLI Reference (v0.3)

## Commands

### `run` - Execute AI tasks

```bash
python3 scripts/collaborate.py run [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Single provider: `codex`, `claude`, `gemini` |
| `--message` | `-m` | Prompt message (single-provider or `--all`) |
| `--tasks` | `-T` | Multiple task specs: `provider:prompt[:id]` |
| `--task-file` | | JSON file with task definitions |
| `--all` | | Run `--message` on all available providers |
| `--dir` | `-d` | Working directory for provider commands |
| `--context` | | Context file path merged into each task prompt |
| `--context-template` | | Template with `{context}` and `{prompt}` (default merges context + prompt) |
| `--timeout` | `-t` | Timeout per task in seconds (default: 300) |
| `--concurrency` | | Max concurrent tasks (default: all tasks) |
| `--format` | `-f` | `text`, `json`, `json-map`, `jsonl` (default: `text`) |
| `--output` | | Write final results to a file |
| `--progress` | | Append per-task results to a JSONL file as they complete |
| `--resume` | | Skip tasks whose ids exist in `--progress` |
| `--resume-failed` | | With `--resume`, re-run tasks previously recorded as failed |
| `--no-fail` | | Always exit 0 (default exits 1 if any task failed) |

### `batch` - Run from JSON file

```bash
python3 scripts/collaborate.py batch <file> [OPTIONS]
```

Supports: `--dir`, `--context`, `--context-template`, `--timeout`, `--concurrency`, `--format`, `--output`, `--progress`, `--resume`, `--resume-failed`, `--no-fail`.

### `status` - Check provider availability

```bash
python3 scripts/collaborate.py status [--format json]
```

### `tokens` - Check API quota hints

```bash
python3 scripts/collaborate.py tokens [--format json]
```

## Task JSON Schema

```json
{
  "tasks": [
    {
      "id": "string (optional, auto-generated if omitted)",
      "provider": "codex | claude | gemini",
      "prompt": "string (required)",
      "context_dir": "string (optional)",
      "context_file": "string (optional)",
      "timeout": "number (optional, default: 300)"
    }
  ]
}
```

## Output formats (run/batch)

### `--format json` (recommended; stable list)

```json
[
  {
    "id": "arch_review",
    "provider": "codex",
    "success": true,
    "returncode": 0,
    "timed_out": false,
    "cancelled": false,
    "output": "…",
    "error": "",
    "execution_time": 8.23,
    "timestamp": "2026-01-29T10:30:00"
  }
]
```

### `--format json-map` (legacy; id-keyed map)

```json
{
  "arch_review": {
    "id": "arch_review",
    "provider": "codex",
    "success": true,
    "returncode": 0,
    "timed_out": false,
    "cancelled": false,
    "output": "…",
    "error": "",
    "execution_time": 8.23,
    "timestamp": "2026-01-29T10:30:00"
  }
}
```

### `--format jsonl` (stream)

One JSON object per line (same shape as list entries).

## Utility scripts

- `scripts/embed_prd_to_tasks.py`: inject/replace context into `tasks.json` prompts via a placeholder.
- `scripts/normalize_results.py`: normalize `json`/`json-map` results into a list for downstream parsing.

