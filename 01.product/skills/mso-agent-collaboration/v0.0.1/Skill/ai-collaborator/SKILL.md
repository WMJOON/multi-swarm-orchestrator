---
name: ai-collaborator
description: Unified multi-agent collaboration skill. Default is collaborate-first (`run`/`batch`); `swarm` is opt-in only when explicitly requested.
allowed-tools: Bash(python3:*,tmux:*)
---

# AI Collaborator

Unified CLI for Codex, Claude, Gemini, and Antigravity collaboration.

## Trigger Policy (Collaborate-first)

1. Default mode is always collaborate execution:
   - `python3 scripts/collaborate.py run ...`
   - `python3 scripts/collaborate.py batch ...`
2. Use `swarm` only when the user explicitly asks for one of:
   - "swarm", "tmux", "queue", "handoff bus"
3. If user intent is ambiguous, ask exactly one choice question before execution:
   - `일회성 병렬 실행(run/batch) vs 지속 스웜(swarm) 중 무엇으로 진행할까요?`

## Quick Start

```bash
# Provider availability
python3 scripts/collaborate.py status

# Collaborate-first: one prompt to all available providers
python3 scripts/collaborate.py run --all -m "Review this design" --format json

# Explicit swarm path (only when requested)
python3 scripts/collaborate.py swarm init --db /tmp/ai-collaborator.db
python3 scripts/collaborate.py swarm start \
  --db /tmp/ai-collaborator.db \
  --session collab \
  --agents planner:claude,coder:codex,reviewer:antigravity
```

## Providers

Supported providers are fixed:
- `codex`
- `claude`
- `gemini`
- `antigravity`

Antigravity policy:
- `ANTIGRAVITY_CMD_TEMPLATE` is mandatory.
- No automatic inference/fallback invocation.

## Data Contracts

Maintained schemas:
- `schemas/task-handoff.schema.json`
- `schemas/output-report.schema.json`
- `schemas/run-manifest.schema.json`
- `schemas/bus-message.schema.json`

Validation mode:
- Default: warn-and-continue
- Strict mode: `--strict-schema` hard fail

Run-level manifests are recorded under:
- `history/runs/*.run-manifest.json`
- `history/swarm/*.run-manifest.json`
