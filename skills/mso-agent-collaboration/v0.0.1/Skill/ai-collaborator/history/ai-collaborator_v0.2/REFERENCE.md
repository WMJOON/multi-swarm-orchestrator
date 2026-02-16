# CLI Reference

## Commands

### `run` - Execute AI tasks

```bash
python3 scripts/collaborate.py run [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--provider` | `-p` | Single provider: `codex`, `claude`, `gemini` |
| `--message` | `-m` | Prompt message |
| `--tasks` | `-T` | Multiple task specs: `provider:prompt[:id]` |
| `--task-file` | | JSON file with task definitions |
| `--all` | | Run on all available providers |
| `--dir` | `-d` | Working directory for commands |
| `--timeout` | `-t` | Timeout per task in seconds (default: 300) |
| `--format` | `-f` | Output format: `text` or `json` |

### `batch` - Run from JSON file

```bash
python3 scripts/collaborate.py batch <file> [--format json]
```

### `status` - Check provider availability

```bash
python3 scripts/collaborate.py status [--format json]
```

### `tokens` - Check API quota status

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
      "timeout": "number (optional, default: 300)"
    }
  ]
}
```

## Output Formats

### Text Format

```
Executing 2 task(s) asynchronously...

============================================================
AI COLLABORATOR RESULTS
============================================================

--- [task_id] PROVIDER ---
Status: SUCCESS
Execution Time: 8.23s

Output:
[AI response here]
----------------------------------------
```

### JSON Format

```json
{
  "task_id": {
    "id": "task_id",
    "provider": "claude",
    "success": true,
    "output": "AI response...",
    "error": "",
    "execution_time": 8.23,
    "timestamp": "2025-01-20T10:30:00"
  }
}
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `CLI not found` | Provider not installed | Install the CLI or remove from task |
| `Command timed out` | Exceeded timeout | Increase `--timeout` value |
| `API errors` | Rate limit / auth issue | Check `tokens` command |

## Token Dashboard Links

| Provider | Dashboard |
|----------|-----------|
| OpenAI (Codex) | https://platform.openai.com/usage |
| Anthropic (Claude) | https://console.anthropic.com/settings/usage |
| Google (Gemini) | https://aistudio.google.com/apikey |

## Legacy Compatibility

v0.1 syntax still works:

```bash
python3 scripts/collaborate.py --provider codex --message "Your prompt"
```
