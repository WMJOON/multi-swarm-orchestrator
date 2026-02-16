from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import bus, swarm
from .executor import run_batch_async
from .providers import check_provider_status, check_token_usage, find_executable, provider_names
from .schemas import SchemaValidationError, validate_run_manifest
from .utils import (
    DEFAULT_CONTEXT_TEMPLATE,
    TaskRequest,
    TaskResult,
    exit_code_for_results,
    load_context_text,
    load_resume_ids,
    normalize_context_args,
    parse_task_spec,
    print_results,
    read_task_file,
    write_output_file,
)

SKILL_ROOT = Path(__file__).resolve().parents[2]
RUN_HISTORY_DIR = SKILL_ROOT / "history" / "runs"
SYSTEM_RULES_TEXT = (
    "collaborate-first;swarm-explicit-only;"
    "providers=codex,claude,gemini,antigravity;"
    "schema=warn-and-continue"
)


def _sha256_prefixed(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _stable_run_id(tasks: Sequence[TaskRequest], started_at: datetime) -> str:
    seed = started_at.isoformat() + "|" + "|".join(f"{t.provider}:{t.id}:{t.timeout}" for t in tasks)
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
    return f"run-{started_at.strftime('%Y%m%d')}-{suffix}"


def _task_status(result: TaskResult) -> str:
    if result.success:
        return "success"
    if result.timed_out:
        return "timeout"
    return "failure"


def _task_exit_code(result: TaskResult) -> str:
    if result.success:
        return "E-000"
    if result.timed_out:
        return "X-001"
    return "S-001"


def _build_run_manifest(tasks: Sequence[TaskRequest], results: Sequence[TaskResult], started_at: datetime, completed_at: datetime) -> Dict[str, Any]:
    result_by_id = {r.id: r for r in results}
    run_id = _stable_run_id(tasks, started_at)

    task_rows: List[Dict[str, Any]] = []
    for idx, task in enumerate(tasks, start=1):
        task_id = task.id or f"task-{idx:03d}"
        result = result_by_id.get(task.id)

        if result is None:
            status = "blocked"
            exit_code = "S-001"
        else:
            status = _task_status(result)
            exit_code = _task_exit_code(result)

        row: Dict[str, Any] = {
            "task_id": task_id,
            "owner_agent": task.provider,
            "status": status,
            "exit_code": exit_code,
        }
        task_rows.append(row)

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    duration = max(0.0, (completed_at - started_at).total_seconds())

    if task_rows and all(t["status"] == "success" for t in task_rows):
        run_status = "completed"
        completed_at_value: Optional[str] = completed_at.isoformat()
    elif any(t["status"] in {"failure", "timeout", "blocked"} for t in task_rows):
        run_status = "failed"
        completed_at_value = completed_at.isoformat()
    else:
        run_status = "in_progress"
        completed_at_value = None

    config_blob = json.dumps(
        [
            {
                "id": t.id,
                "provider": t.provider,
                "timeout": t.timeout,
                "context_dir": t.context_dir,
                "context_file": t.context_file,
            }
            for t in tasks
        ],
        ensure_ascii=False,
        sort_keys=True,
    )

    return {
        "run_id": run_id,
        "created_at": started_at.isoformat(),
        "completed_at": completed_at_value,
        "status": run_status,
        "tasks": task_rows,
        "config_hash": _sha256_prefixed(config_blob),
        "system_rules_hash": _sha256_prefixed(SYSTEM_RULES_TEXT),
        "aggregate_metrics": {
            "total_tasks": len(tasks),
            "succeeded": succeeded,
            "failed": failed,
            "total_duration_seconds": duration,
            "total_tokens": 0,
            "retry_total": 0,
            "conflict_count": 0,
        },
    }


def _persist_run_manifest(manifest: Dict[str, Any], strict_schema: bool) -> Path:
    warnings = validate_run_manifest(manifest, strict=strict_schema)
    for warning in warnings:
        print(f"[warn] run manifest schema: {warning}", file=sys.stderr)

    RUN_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUN_HISTORY_DIR / f"{manifest['run_id']}.run-manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def _print_status(status: Dict[str, Dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"type": "status", "timestamp": datetime.now().isoformat(), "providers": status}, indent=2))
        return

    print("\n=== AI Provider Status ===\n")
    for provider, info in status.items():
        icon = "✓" if info["available"] else "✗"
        print(f"{icon} {provider}: {'Available' if info['available'] else 'Not found'}")
        if info["available"]:
            print(f"  Path: {info['path']}")
        print(f"  {info['description']}\n")


def _print_tokens(info: Dict[str, Dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"type": "tokens", "timestamp": datetime.now().isoformat(), "providers": info}, indent=2))
        return

    print("\n=== Token/Quota Status ===\n")
    for _provider, item in info.items():
        icon = "✓" if item.get("api_key_set") else "✗"
        print(f"{icon} {item['provider']}")
        print(f"  API Key: {'Set' if item.get('api_key_set') else 'Not set'}")
        print(f"  Note: {item['note']}")
        if item.get("check_method"):
            print(f"  Check: {item['check_method']}")
        print()


def _read_tasks_for_run(args: argparse.Namespace, context_dir: Optional[str]) -> List[TaskRequest]:
    tasks: List[TaskRequest] = []
    allowed = provider_names()

    if args.task_file:
        for i, t in enumerate(read_task_file(args.task_file)):
            tasks.append(
                TaskRequest(
                    id=t.get("id", f"task_{i}"),
                    provider=t["provider"],
                    prompt=t["prompt"],
                    context_dir=t.get("context_dir", context_dir),
                    context_file=t.get("context_file"),
                    timeout=t.get("timeout", args.timeout),
                )
            )
    elif args.tasks:
        for spec in args.tasks:
            task = parse_task_spec(spec, allowed)
            task.context_dir = context_dir
            task.timeout = args.timeout
            tasks.append(task)
    elif args.provider and args.message:
        tasks.append(
            TaskRequest(
                id=f"{args.provider}_0",
                provider=args.provider,
                prompt=args.message,
                context_dir=context_dir,
                timeout=args.timeout,
            )
        )
    elif args.all and args.message:
        for i, provider in enumerate(allowed):
            if find_executable(provider):
                tasks.append(
                    TaskRequest(
                        id=f"{provider}_{i}",
                        provider=provider,
                        prompt=args.message,
                        context_dir=context_dir,
                        timeout=args.timeout,
                    )
                )
    else:
        raise ValueError("Specify --provider/-m, --tasks, --task-file, or --all/-m")

    return tasks


def _read_tasks_for_batch(args: argparse.Namespace, context_dir: Optional[str]) -> List[TaskRequest]:
    tasks: List[TaskRequest] = []

    for i, t in enumerate(read_task_file(args.file)):
        tasks.append(
            TaskRequest(
                id=t.get("id", f"task_{i}"),
                provider=t["provider"],
                prompt=t["prompt"],
                context_dir=t.get("context_dir", context_dir),
                context_file=t.get("context_file"),
                timeout=t.get("timeout", args.timeout),
            )
        )

    return tasks


def _apply_resume(tasks: List[TaskRequest], args: argparse.Namespace) -> List[TaskRequest]:
    if not args.resume:
        return tasks
    seen = load_resume_ids(args.progress, resume_failed=args.resume_failed)
    return [t for t in tasks if t.id not in seen]


def _run_tasks(args: argparse.Namespace) -> int:
    context_file, context_dir = normalize_context_args(getattr(args, "context", None), getattr(args, "dir", None))

    global_context_text = ""
    if context_file:
        global_context_text = load_context_text(context_file, args.context_encoding, args.context_max_chars)

    if args.command == "run":
        tasks = _read_tasks_for_run(args, context_dir)
    else:
        tasks = _read_tasks_for_batch(args, context_dir)

    if not tasks:
        print("Error: No valid tasks to execute", file=sys.stderr)
        return 2

    if args.resume and not args.progress:
        print("Error: --resume requires --progress", file=sys.stderr)
        return 2

    tasks = _apply_resume(tasks, args)
    if not tasks:
        print("Error: No valid tasks to execute", file=sys.stderr)
        return 2

    concurrency = args.concurrency if args.concurrency and args.concurrency > 0 else len(tasks)

    started_at = datetime.now(timezone.utc)
    try:
        print(f"Executing {len(tasks)} task(s) asynchronously...\n")
        results = asyncio.run(
            run_batch_async(
                tasks,
                concurrency=concurrency,
                progress_path=args.progress,
                global_context_text=global_context_text,
                context_template=args.context_template,
                context_encoding=args.context_encoding,
                context_max_chars=args.context_max_chars,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.\n", file=sys.stderr)
        return 130

    print_results(results, args.format)
    if args.output:
        write_output_file(args.output, results, args.format)

    completed_at = datetime.now(timezone.utc)
    manifest = _build_run_manifest(tasks, results, started_at, completed_at)
    manifest_path = _persist_run_manifest(manifest, strict_schema=args.strict_schema)
    print(f"\nRun manifest: {manifest_path}", file=sys.stderr)

    return exit_code_for_results(results, no_fail=args.no_fail)


def _add_shared_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dir", "-d", help="Working directory for commands")
    parser.add_argument("--context", help="Context file path merged into each task prompt")
    parser.add_argument(
        "--context-template",
        default=DEFAULT_CONTEXT_TEMPLATE,
        help="Template for merging context into prompt (use {context} and {prompt})",
    )
    parser.add_argument("--context-encoding", default="utf-8", help="Encoding for --context/context_file (default: utf-8)")
    parser.add_argument(
        "--context-max-chars",
        type=int,
        default=None,
        help="Max chars to read from context file(s) (default: unlimited)",
    )
    parser.add_argument("--timeout", "-t", type=int, default=300, help="Timeout per task in seconds (default: 300)")
    parser.add_argument("--concurrency", type=int, default=0, help="Max concurrent tasks (default: all tasks)")
    parser.add_argument("--format", "-f", choices=["text", "json", "json-map", "jsonl"], default="text")
    parser.add_argument("--output", help="Write final results to a file")
    parser.add_argument("--progress", help="Append per-task results to a JSONL file as they complete")
    parser.add_argument("--resume", action="store_true", help="Skip tasks whose ids exist in --progress")
    parser.add_argument(
        "--resume-failed",
        action="store_true",
        help="With --resume, re-run tasks previously recorded as failed (skip only successes)",
    )
    parser.add_argument("--no-fail", action="store_true", help="Always exit 0 (default exits 1 if any task failed)")
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help="Hard-fail schema validation instead of warn-and-continue",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Collaborator v0.4 - Unified collaborate + swarm")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    providers = provider_names()

    run_parser = subparsers.add_parser("run", help="Run AI command(s)")
    run_parser.add_argument("--provider", "-p", choices=providers, help="Single provider to use (with --message)")
    run_parser.add_argument("--message", "-m", help="Prompt message for single provider mode")
    run_parser.add_argument(
        "--tasks",
        "-T",
        nargs="+",
        help="Multiple task specs: 'provider:prompt[:id]'",
    )
    run_parser.add_argument("--task-file", help="JSON file with task definitions ('-' for stdin)")
    run_parser.add_argument("--all", action="store_true", help="Run --message on all available providers")
    _add_shared_run_args(run_parser)

    batch_parser = subparsers.add_parser("batch", help="Run batch from JSON file")
    batch_parser.add_argument("file", help="JSON file with task definitions ('-' for stdin)")
    _add_shared_run_args(batch_parser)

    status_parser = subparsers.add_parser("status", help="Check provider availability")
    status_parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    token_parser = subparsers.add_parser("tokens", help="Check token/quota status")
    token_parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    swarm_parser = subparsers.add_parser("swarm", help="Persistent tmux-based swarm orchestration")
    swarm_sub = swarm_parser.add_subparsers(dest="swarm_command", required=True)

    swarm_init = swarm_sub.add_parser("init", help="Initialize swarm bus database")
    swarm_init.add_argument("--db", required=True, help="Path to sqlite bus database")

    swarm_start = swarm_sub.add_parser("start", help="Start tmux swarm session")
    swarm_start.add_argument("--db", required=True, help="Path to sqlite bus database")
    swarm_start.add_argument("--session", required=True, help="tmux session name")
    swarm_start.add_argument("--agents", required=True, help="agent map, e.g. planner:claude,coder:codex")
    swarm_start.add_argument("--poll-seconds", type=float, default=2.0)
    swarm_start.add_argument("--lease-seconds", type=int, default=60)
    swarm_start.add_argument("--max-attempts", type=int, default=3)
    swarm_start.add_argument("--inspect-interval", type=int, default=2)
    swarm_start.add_argument("--strict-schema", action="store_true")

    swarm_send = swarm_sub.add_parser("send", help="Send one message into swarm bus")
    swarm_send.add_argument("--db", required=True, help="Path to sqlite bus database")
    swarm_send.add_argument("--from", dest="from_agent", required=True)
    swarm_send.add_argument("--to", dest="to_agent", required=True)
    swarm_send.add_argument("--type", dest="msg_type", required=True)
    swarm_send.add_argument("--payload", required=True, help="JSON payload string")
    swarm_send.add_argument("--trace-id")
    swarm_send.add_argument("--thread-id")
    swarm_send.add_argument("--strict-schema", action="store_true")

    swarm_inspect = swarm_sub.add_parser("inspect", help="Live inspect swarm queue status")
    swarm_inspect.add_argument("--db", required=True, help="Path to sqlite bus database")
    swarm_inspect.add_argument("--interval", type=int, default=2)

    swarm_stop = swarm_sub.add_parser("stop", help="Stop a tmux swarm session")
    swarm_stop.add_argument("--session", required=True, help="tmux session name")

    # Internal helper used by tmux windows created by `swarm start`.
    swarm_worker = swarm_sub.add_parser("worker", help=argparse.SUPPRESS)
    swarm_worker.add_argument("--db", required=True, help="Path to sqlite bus database")
    swarm_worker.add_argument("--agent", required=True)
    swarm_worker.add_argument("--provider", choices=providers, required=True)
    swarm_worker.add_argument("--poll-seconds", type=float, default=2.0)
    swarm_worker.add_argument("--lease-seconds", type=int, default=60)
    swarm_worker.add_argument("--max-attempts", type=int, default=3)
    swarm_worker.add_argument("--task-timeout", type=int, default=300)
    swarm_worker.add_argument("--strict-schema", action="store_true")

    # Legacy flags support
    parser.add_argument("--provider", choices=providers, help="(Legacy) AI Provider")
    parser.add_argument("--message", help="(Legacy) Prompt message")
    parser.add_argument("--dir", help="(Legacy) Working directory")
    parser.add_argument("--context", help="(Legacy) Context file path merged into prompt")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command is None and getattr(args, "provider", None) and getattr(args, "message", None):
            context_file, context_dir = normalize_context_args(getattr(args, "context", None), getattr(args, "dir", None))
            global_context_text = ""
            if context_file:
                global_context_text = load_context_text(context_file, "utf-8", None)

            task = TaskRequest(
                id=f"{args.provider}_0",
                provider=args.provider,
                prompt=args.message,
                context_dir=context_dir,
            )
            results = asyncio.run(
                run_batch_async(
                    [task],
                    concurrency=1,
                    progress_path=None,
                    global_context_text=global_context_text,
                    context_template=DEFAULT_CONTEXT_TEMPLATE,
                    context_encoding="utf-8",
                    context_max_chars=None,
                )
            )
            if results[0].success:
                print(results[0].output)
                sys.exit(0)
            print(f"Error: {results[0].error}", file=sys.stderr)
            sys.exit(1)

        if args.command == "status":
            _print_status(check_provider_status(), args.format)
            return

        if args.command == "tokens":
            _print_tokens(check_token_usage(), args.format)
            return

        if args.command == "swarm":
            if args.swarm_command == "init":
                bus.init_bus(args.db)
                print(f"initialized swarm bus: {args.db}")
                return

            if args.swarm_command == "start":
                bus.init_bus(args.db)
                swarm.start_swarm_session(
                    db_path=args.db,
                    session=args.session,
                    agents_spec=args.agents,
                    strict_schema=args.strict_schema,
                    poll_seconds=args.poll_seconds,
                    lease_seconds=args.lease_seconds,
                    max_attempts=args.max_attempts,
                    inspect_interval=args.inspect_interval,
                )
                return

            if args.swarm_command == "send":
                bus.init_bus(args.db)
                swarm.send_swarm_message(
                    db_path=args.db,
                    from_agent=args.from_agent,
                    to_agent=args.to_agent,
                    msg_type=args.msg_type,
                    payload_raw=args.payload,
                    trace_id=args.trace_id,
                    thread_id=args.thread_id,
                    strict_schema=args.strict_schema,
                )
                return

            if args.swarm_command == "inspect":
                bus.init_bus(args.db)
                swarm.inspect_swarm(args.db, interval=args.interval)
                return

            if args.swarm_command == "stop":
                swarm.stop_swarm_session(args.session)
                return

            if args.swarm_command == "worker":
                bus.init_bus(args.db)
                swarm.run_worker_loop(
                    db_path=args.db,
                    agent=args.agent,
                    provider=args.provider,
                    strict_schema=args.strict_schema,
                    poll_seconds=args.poll_seconds,
                    lease_seconds=args.lease_seconds,
                    max_attempts=args.max_attempts,
                    task_timeout=args.task_timeout,
                )
                return

        if args.command in {"run", "batch"}:
            code = _run_tasks(args)
            sys.exit(code)

        parser.print_help()

    except SchemaValidationError as e:
        print(f"Schema error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
