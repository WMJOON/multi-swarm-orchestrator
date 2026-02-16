---
name: ai-collaborator
description: Run multiple AI CLI tools (Codex, Claude, Gemini) concurrently with different prompts. Use when needing second opinions, cross-verification, parallel reviews, or multi-model comparison.
allowed-tools: Bash(python3:*)
---

# AI Collaborator

Unified async interface for Codex, Claude Code, and Gemini CLIs.

## Quick Start

```bash
# Single provider
python3 scripts/collaborate.py run -p claude -m "Review this code"

# Multiple providers, same prompt
python3 scripts/collaborate.py run --all -m "Is this architecture good?"

# Multiple providers, different prompts (async)
python3 scripts/collaborate.py run --tasks \
  "claude:Security review" \
  "gemini:Performance check" \
  "codex:Architecture review"
```

## Providers

| Provider | Best For |
|----------|----------|
| `codex` | AI strategy, general reasoning |
| `claude` | Code analysis, logical critique |
| `gemini` | Google ecosystem, localized context |

## Commands

```bash
# Check which CLIs are available
python3 scripts/collaborate.py status

# Check API key / quota status
python3 scripts/collaborate.py tokens

# Batch from JSON file
python3 scripts/collaborate.py batch tasks.json --format json
```

## Task Spec Format

Inline: `provider:prompt[:id]`

```bash
python3 scripts/collaborate.py run --tasks \
  "claude:Find bugs:bug_check" \
  "gemini:Optimize performance:perf_task"
```

JSON file (`tasks.json`):
```json
{
  "tasks": [
    {"id": "task1", "provider": "claude", "prompt": "...", "timeout": 300},
    {"id": "task2", "provider": "gemini", "prompt": "..."}
  ]
}
```

## Workflow Patterns

See [PATTERNS.md](../PATTERNS.md) for detailed examples:
- Council of Elders (multi-model consensus)
- Parallel Specialized Reviews
- Triangulation (tiebreaker)
- Pipeline Integration

## Options Reference

See [REFERENCE.md](../REFERENCE.md) for complete CLI options and output formats.
