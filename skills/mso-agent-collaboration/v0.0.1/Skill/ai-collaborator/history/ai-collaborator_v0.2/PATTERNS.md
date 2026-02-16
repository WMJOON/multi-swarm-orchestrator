# Workflow Patterns

## Pattern A: Council of Elders

Get multiple perspectives on a critical decision:

```bash
python3 scripts/collaborate.py run --all \
  -m "Act as a Senior Architect. Should we use microservices or monolith for this project? Context: [details]" \
  --format json
```

## Pattern B: Parallel Specialized Reviews

Run different analysis types simultaneously:

```bash
python3 scripts/collaborate.py run --tasks \
  "claude:Act as a security expert. Find vulnerabilities in: [code]" \
  "gemini:Act as a performance engineer. Find bottlenecks in: [code]" \
  "codex:Act as an architect. Review the design of: [code]"
```

## Pattern C: Triangulation

When two providers disagree, use the third as tiebreaker:

```bash
# First: Get two opinions
python3 scripts/collaborate.py run --tasks \
  "claude:Should we use Redux or Context API?" \
  "gemini:Should we use Redux or Context API?"

# Then: Tiebreaker with context
python3 scripts/collaborate.py run -p codex \
  -m "Claude says X, Gemini says Y. Which is better for [context]?"
```

## Pattern D: Batch Processing

For complex workflows, define tasks in JSON:

```bash
python3 scripts/collaborate.py batch tasks.json --format json > results.json
```

Example `tasks.json`:
```json
{
  "tasks": [
    {
      "id": "security_review",
      "provider": "claude",
      "prompt": "Review this code for security vulnerabilities: [code]",
      "timeout": 300
    },
    {
      "id": "perf_analysis",
      "provider": "gemini",
      "prompt": "Analyze performance and suggest optimizations: [code]"
    },
    {
      "id": "arch_review",
      "provider": "codex",
      "prompt": "Review the architecture design: [code]",
      "context_dir": "/path/to/project"
    }
  ]
}
```

## Pattern E: Pipeline Integration

Generate JSON output for downstream processing:

```bash
python3 scripts/collaborate.py run --tasks \
  "claude:Summarize this document" \
  "gemini:Extract key points" \
  --format json | jq '.[] | select(.success == true)'
```

## Best Practices

- **Persona prompting**: Always instruct the AI to act as a "Senior Specialist" or "Red Team Critic"
- **Context**: Provide relevant file paths or content snippets in the prompt
- **Rate limits**: Space out batch operations if hitting API limits
- **Timeout**: Use `--timeout` to prevent hanging requests (default: 300s)
