# Workflow Patterns (Unified)

## 1. Collaborate-only

Use when you need one-shot parallel opinions without persistent queue workers.

```bash
python3 scripts/collaborate.py run --context ./PRD.md --tasks \
  "claude:Review architecture assumptions:task-001" \
  "codex:Find implementation risks:task-002" \
  "gemini:Check metric feasibility:task-003" \
  --format json
```

## 2. Hybrid (run + swarm)

Use `run` first for fast triage, then escalate selected work to `swarm`.

```bash
# Fast triage
python3 scripts/collaborate.py run --all -m "Identify top 3 risky modules" --format json

# Escalate to persistent swarm only for selected task
python3 scripts/collaborate.py swarm init --db /tmp/ai-collaborator.db
python3 scripts/collaborate.py swarm start \
  --db /tmp/ai-collaborator.db \
  --session collab \
  --agents planner:claude,coder:codex,reviewer:antigravity
python3 scripts/collaborate.py swarm send \
  --db /tmp/ai-collaborator.db \
  --from planner \
  --to coder \
  --type TASK_REQUEST \
  --payload '{"goal":"Refactor module X with tests"}'
```

## 3. Long-running swarm (inspect + retry/dead)

Use when work must survive retries and be observed continuously.

```bash
python3 scripts/collaborate.py swarm init --db /tmp/ai-collaborator.db
python3 scripts/collaborate.py swarm start \
  --db /tmp/ai-collaborator.db \
  --session longrun \
  --agents planner:claude,worker:antigravity \
  --lease-seconds 30 \
  --max-attempts 3

python3 scripts/collaborate.py swarm inspect --db /tmp/ai-collaborator.db --interval 2

# Stop when done
python3 scripts/collaborate.py swarm stop --session longrun
```

Notes:
- `TASK_REQUEST.payload` should follow `task-handoff.schema.json`.
- `TASK_RESULT.payload` should follow `output-report.schema.json`.
- Run-level manifests are recorded automatically.
