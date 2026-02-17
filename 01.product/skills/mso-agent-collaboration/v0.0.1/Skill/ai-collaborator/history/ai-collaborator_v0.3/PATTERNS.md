# Workflow Patterns (v0.3)

## Pattern A: Council of Elders (Same prompt, multiple providers)

```bash
python3 scripts/collaborate.py run --all \
  --context ./CONTEXT.md \
  -m "Act as a Senior Architect. Provide critique and risks." \
  --format json
```

## Pattern B: Parallel Specialized Reviews (Different prompts)

```bash
python3 scripts/collaborate.py run --context ./PRD.md --tasks \
  "claude:Act as a security expert. Identify security risks." \
  "gemini:Act as a performance engineer. Identify bottlenecks." \
  "codex:Act as an architect. Challenge assumptions and propose alternatives." \
  --format json
```

## Pattern C: Long run with progress + resume

```bash
python3 scripts/collaborate.py batch tasks.json \
  --context ./PRD.md \
  --progress ./.ai-collaborator.progress.jsonl \
  --resume \
  --format json
```

## Pattern D: Pipeline-friendly output shapes

```bash
# Stable list (recommended)
python3 scripts/collaborate.py run --all -m "Summarize this" --format json

# Legacy map (v0.2-compatible)
python3 scripts/collaborate.py run --all -m "Summarize this" --format json-map

# JSONL stream (one result per line)
python3 scripts/collaborate.py run --all -m "Summarize this" --format jsonl
```

## Best Practices

- Prefer `--context <file>` over `$(cat ...)` to avoid shell quoting/arg issues.
- Use stable ids in `tasks.json` to make `--resume` reliable.
- For very large contexts, split into smaller files and reference the most relevant one.

