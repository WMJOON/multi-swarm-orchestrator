---
name: ai-collaborator
description: Run multiple AI CLI tools (Codex, Claude, Gemini) concurrently with different prompts. Use when needing second opinions, cross-verification, parallel reviews, or multi-model comparison.
allowed-tools: Bash(python3:*)
---

# AI Collaborator (v0.3.1)

Unified async interface for Codex, Claude Code, and Gemini CLIs.

## What changed vs v0.3.0

- **Fix**: Changed execution to use **STDIN** for passing prompts. This resolves `Argument list too long` errors when using large context files (e.g., PRDs).
- **Fix**: Adjusted `claude` CLI arguments to support STDIN mode correctly.

## What changed vs v0.2

- `--context` is now supported (context **file path**) and is merged into each task prompt.
- `--format json` is standardized to a **JSON list** (stable schema); `--format json-map` keeps the old map shape.
- Optional `--progress` (JSONL) + `--resume` for long-running or interruption-prone runs.

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

## Context file (recommended)

Pass a file path once, avoid embedding large context in CLI args:

```bash
python3 scripts/collaborate.py run --all \
  --context ./PRD.md \
  -m "Critique this PRD as a Senior Architect." \
  --format json
```

## Batch from JSON file

```bash
python3 scripts/collaborate.py batch tasks.json \
  --context ./PRD.md \
  --format json \
  --progress ./.ai-collaborator.progress.jsonl \
  --resume
```

## Workflow Patterns

See `PATTERNS.md`.

## Options Reference

See `REFERENCE.md`.

