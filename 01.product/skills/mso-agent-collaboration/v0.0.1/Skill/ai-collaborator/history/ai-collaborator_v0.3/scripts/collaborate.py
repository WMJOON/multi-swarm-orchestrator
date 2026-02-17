#!/usr/bin/env python3
"""
AI Collaborator v0.3
- Async concurrent execution for multiple AI CLIs (Codex, Claude, Gemini)
- Per-task provider/prompt control
- Global/per-task context file merging (via --context / context_file)
- Stable JSON list output (and legacy json-map)
- Optional progress JSONL + resume for long runs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


PROVIDERS: Dict[str, Dict[str, Any]] = {
    "codex": {
        "path": "/Users/wmjoon/.bun/bin/codex",
        "alt_paths": ["/opt/homebrew/bin/codex", "codex"],
        "cmd": ["exec", "--skip-git-repo-check"],
        "description": "OpenAI Codex - Best for overall AX/AI strategy",
    },
    "claude": {
        "path": "/opt/homebrew/bin/claude",
        "alt_paths": ["claude"],
        "cmd": ["-p"],
        "stdin_cmd": [],  # When using STDIN, do not use -p
        "description": "Claude Code - High-performance coding assistant",
    },
    "gemini": {
        "path": "/opt/homebrew/bin/gemini",
        "alt_paths": ["gemini"],
        "cmd": [],
        "description": "Gemini CLI - Strong in Google ecosystem",
    },
}


DEFAULT_CONTEXT_TEMPLATE = "{context}\n\n---\n\n{prompt}"


@dataclass
class TaskRequest:
    id: str
    provider: str
    prompt: str
    context_dir: Optional[str] = None
    context_file: Optional[str] = None
    timeout: int = 300


@dataclass
class TaskResult:
    id: str
    provider: str
    success: bool
    returncode: Optional[int]
    timed_out: bool
    cancelled: bool
    output: str
    error: str
    execution_time: float
    timestamp: str


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def find_executable(provider: str) -> Optional[str]:
    config = PROVIDERS.get(provider)
    if not config:
        return None

    if os.path.exists(config["path"]):
        return config["path"]

    for alt in config.get("alt_paths", []):
        if os.path.exists(alt):
            return alt
        try:
            result = subprocess.run(["which", alt], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    return None


def check_provider_status() -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for provider, config in PROVIDERS.items():
        executable = find_executable(provider)
        status[provider] = {
            "available": executable is not None,
            "path": executable,
            "description": config["description"],
        }
    return status


def check_token_usage() -> Dict[str, Dict[str, Any]]:
    token_info: Dict[str, Dict[str, Any]] = {}

    openai_key = os.environ.get("OPENAI_API_KEY")
    token_info["codex"] = {
        "provider": "OpenAI (Codex)",
        "api_key_set": bool(openai_key),
        "note": "Check usage at https://platform.openai.com/usage"
        if openai_key
        else "OPENAI_API_KEY not found",
        "check_method": "API dashboard" if openai_key else None,
    }

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    token_info["claude"] = {
        "provider": "Anthropic (Claude)",
        "api_key_set": bool(anthropic_key),
        "note": "Check usage at https://console.anthropic.com/settings/usage"
        if anthropic_key
        else "ANTHROPIC_API_KEY not found",
        "check_method": "API dashboard" if anthropic_key else None,
    }

    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    token_info["gemini"] = {
        "provider": "Google (Gemini)",
        "api_key_set": bool(google_key),
        "note": "Check usage at https://aistudio.google.com/apikey"
        if google_key
        else "GOOGLE_API_KEY or GEMINI_API_KEY not found",
        "check_method": "Google AI Studio" if google_key else None,
    }

    return token_info


def parse_task_spec(spec: str) -> TaskRequest:
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid task spec: {spec}. Format: provider:prompt[:id]")

    provider = parts[0].strip()
    prompt = parts[1].strip()
    task_id = parts[2].strip() if len(parts) > 2 else f"{provider}_{hash(prompt) % 10000}"

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDERS.keys())}")

    return TaskRequest(id=task_id, provider=provider, prompt=prompt)


def load_context_text(path: Optional[str], encoding: str, max_chars: Optional[int]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Context file not found: {path}")
    if p.is_dir():
        raise IsADirectoryError(f"Context path is a directory (expected file): {path}")
    text = p.read_text(encoding=encoding)
    if max_chars is not None and max_chars >= 0 and len(text) > max_chars:
        return text[:max_chars]
    return text


def merge_prompt(prompt: str, context: str, template: str) -> str:
    if not context.strip():
        return prompt
    if "{context}" not in template or "{prompt}" not in template:
        template = DEFAULT_CONTEXT_TEMPLATE
    return template.format(context=context, prompt=prompt)


async def _terminate_process(proc: asyncio.subprocess.Process, grace_s: float = 2.0) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()


async def run_ai_command_async(
    task: TaskRequest,
    *,
    global_context_text: str,
    context_template: str,
    context_encoding: str,
    context_max_chars: Optional[int],
) -> TaskResult:
    start = datetime.now()

    if task.provider not in PROVIDERS:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"Provider '{task.provider}' not supported. Available: {list(PROVIDERS.keys())}",
            execution_time=0.0,
            timestamp=start.isoformat(),
        )

    executable = find_executable(task.provider)
    if not executable:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"{task.provider} CLI not found on system.",
            execution_time=0.0,
            timestamp=start.isoformat(),
        )

    task_context_text = ""
    if task.context_file:
        try:
            task_context_text = load_context_text(task.context_file, context_encoding, context_max_chars)
        except Exception as e:
            return TaskResult(
                id=task.id,
                provider=task.provider,
                success=False,
                returncode=None,
                timed_out=False,
                cancelled=False,
                output="",
                error=f"Failed to read task context_file ({task.context_file}): {e}",
                execution_time=(datetime.now() - start).total_seconds(),
                timestamp=start.isoformat(),
            )

    combined_context = "\n\n".join([c for c in [global_context_text, task_context_text] if c.strip()])
    final_prompt = merge_prompt(task.prompt, combined_context, context_template)

    # Prepare command - use STDIN for prompt to avoid OS argument limit (E2BIG)
    provider_config = PROVIDERS[task.provider]
    cmd_args = provider_config.get("stdin_cmd", provider_config["cmd"]) # Use stdin_cmd if available, else default cmd
    full_cmd = [executable] + list(cmd_args)

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            cwd=task.context_dir if task.context_dir else os.getcwd(),
            stdin=asyncio.subprocess.PIPE,  # Always use PIPE for stdin
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Pass final_prompt via STDIN
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=final_prompt.encode("utf-8")), 
                timeout=task.timeout
            )
            output = stdout.decode(errors="replace") if stdout else ""
            err = stderr.decode(errors="replace") if stderr else ""
            success = proc.returncode == 0
            return TaskResult(
                id=task.id,
                provider=task.provider,
                success=success,
                returncode=proc.returncode,
                timed_out=False,
                cancelled=False,
                output=output,
                error=err if not success else "",
                execution_time=(datetime.now() - start).total_seconds(),
                timestamp=start.isoformat(),
            )

        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return TaskResult(
                id=task.id,
                provider=task.provider,
                success=False,
                returncode=proc.returncode,
                timed_out=True,
                cancelled=False,
                output="",
                error=f"Command timed out after {task.timeout} seconds",
                execution_time=(datetime.now() - start).total_seconds(),
                timestamp=start.isoformat(),
            )

        except asyncio.CancelledError:
            await _terminate_process(proc)
            raise

    except Exception as e:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"Unexpected error: {e}",
            execution_time=(datetime.now() - start).total_seconds(),
            timestamp=start.isoformat(),
        )


def _read_task_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    if isinstance(task_data, list):
        return task_data
    return task_data.get("tasks", [])


def _load_resume_ids(progress_path: str, *, resume_failed: bool) -> Dict[str, bool]:
    """
    Returns a mapping of task_id -> last_success (bool).
    """
    p = Path(progress_path)
    if not p.exists():
        return {}

    seen: Dict[str, bool] = {}
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            task_id = obj.get("id")
            if not task_id:
                continue
            success = bool(obj.get("success"))
            seen[task_id] = success

    if resume_failed:
        return {k: v for k, v in seen.items() if v is True}
    return seen


def _append_progress(progress_path: str, result: TaskResult) -> None:
    Path(progress_path).parent.mkdir(parents=True, exist_ok=True)
    with open(progress_path, "a", encoding="utf-8") as f:
        f.write(_json_dumps(asdict(result)) + "\n")


async def run_batch_async(
    tasks: Sequence[TaskRequest],
    *,
    concurrency: int,
    progress_path: Optional[str],
    global_context_text: str,
    context_template: str,
    context_encoding: str,
    context_max_chars: Optional[int],
) -> List[TaskResult]:
    semaphore = asyncio.Semaphore(concurrency)

    async def runner(t: TaskRequest) -> TaskResult:
        async with semaphore:
            res = await run_ai_command_async(
                t,
                global_context_text=global_context_text,
                context_template=context_template,
                context_encoding=context_encoding,
                context_max_chars=context_max_chars,
            )
            if progress_path:
                _append_progress(progress_path, res)
            return res

    coros = [runner(t) for t in tasks]
    return await asyncio.gather(*coros)


def print_results(results: List[TaskResult], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        return
    if fmt == "json-map":
        print(
            json.dumps(
                {r.id: asdict(r) for r in results},
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if fmt == "jsonl":
        for r in results:
            print(_json_dumps(asdict(r)))
        return

    print(_format_text_results(results))


def _format_text_results(results: List[TaskResult]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("AI COLLABORATOR RESULTS")
    lines.append("=" * 60)

    for r in results:
        lines.append("")
        lines.append(f"--- [{r.id}] {r.provider.upper()} ---")
        lines.append(f"Status: {'SUCCESS' if r.success else 'FAILED'}")
        lines.append(f"Execution Time: {r.execution_time:.2f}s")
        if r.timed_out:
            lines.append("Timed out: true")
        if r.returncode is not None:
            lines.append(f"Return code: {r.returncode}")

        if r.output:
            lines.append("")
            lines.append("Output:")
            lines.append(r.output.rstrip("\n"))

        if r.error:
            lines.append("")
            lines.append("Error:")
            lines.append(r.error.rstrip("\n"))

        lines.append("-" * 40)

    lines.append("")
    return "\n".join(lines)


def _write_output_file(path: str, results: List[TaskResult], fmt: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        p.write_text(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if fmt == "json-map":
        p.write_text(json.dumps({r.id: asdict(r) for r in results}, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if fmt == "jsonl":
        p.write_text("\n".join(_json_dumps(asdict(r)) for r in results) + "\n", encoding="utf-8")
        return
    p.write_text(_format_text_results(results), encoding="utf-8")


def _normalize_context_args(context_path: Optional[str], dir_path: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    If --context points to a directory, treat it as --dir for compatibility.
    Returns (context_file, context_dir).
    """
    if not context_path:
        return None, dir_path
    p = Path(context_path)
    if p.exists() and p.is_dir():
        if dir_path:
            print(
                f"Warning: --context '{context_path}' is a directory; ignoring it because --dir is set.",
                file=sys.stderr,
            )
            return None, dir_path
        print(
            f"Warning: --context '{context_path}' is a directory; treating it as --dir.",
            file=sys.stderr,
        )
        return None, context_path
    return context_path, dir_path


def _exit_code_for_results(results: List[TaskResult], *, no_fail: bool) -> int:
    if no_fail:
        return 0
    return 0 if all(r.success for r in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Collaborator v0.3 - Async multi-provider execution")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    def add_shared_run_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dir", "-d", help="Working directory for commands")
        p.add_argument("--context", help="Context file path merged into each task prompt")
        p.add_argument(
            "--context-template",
            default=DEFAULT_CONTEXT_TEMPLATE,
            help="Template for merging context into prompt (use {context} and {prompt})",
        )
        p.add_argument("--context-encoding", default="utf-8", help="Encoding for --context/context_file (default: utf-8)")
        p.add_argument(
            "--context-max-chars",
            type=int,
            default=None,
            help="Max chars to read from context file(s) (default: unlimited)",
        )
        p.add_argument("--timeout", "-t", type=int, default=300, help="Timeout per task in seconds (default: 300)")
        p.add_argument("--concurrency", type=int, default=0, help="Max concurrent tasks (default: all tasks)")
        p.add_argument("--format", "-f", choices=["text", "json", "json-map", "jsonl"], default="text")
        p.add_argument("--output", help="Write final results to a file")
        p.add_argument("--progress", help="Append per-task results to a JSONL file as they complete")
        p.add_argument("--resume", action="store_true", help="Skip tasks whose ids exist in --progress")
        p.add_argument(
            "--resume-failed",
            action="store_true",
            help="With --resume, re-run tasks previously recorded as failed (skip only successes)",
        )
        p.add_argument("--no-fail", action="store_true", help="Always exit 0 (default exits 1 if any task failed)")

    run_parser = subparsers.add_parser("run", help="Run AI command(s)")
    run_parser.add_argument("--provider", "-p", choices=list(PROVIDERS.keys()), help="Single provider to use (with --message)")
    run_parser.add_argument("--message", "-m", help="Prompt message for single provider mode")
    run_parser.add_argument(
        "--tasks",
        "-T",
        nargs="+",
        help="Multiple task specs: 'provider:prompt[:id]' (e.g., 'claude:Review code:code_review')",
    )
    run_parser.add_argument("--task-file", help="JSON file with task definitions")
    run_parser.add_argument("--all", action="store_true", help="Run --message on all available providers")
    add_shared_run_args(run_parser)

    batch_parser = subparsers.add_parser("batch", help="Run batch from JSON file")
    batch_parser.add_argument("file", help="JSON file with task definitions")
    add_shared_run_args(batch_parser)

    status_parser = subparsers.add_parser("status", help="Check provider availability")
    status_parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    token_parser = subparsers.add_parser("tokens", help="Check token/quota status")
    token_parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    # Legacy flags support
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), help="(Legacy) AI Provider")
    parser.add_argument("--message", help="(Legacy) Prompt message")
    parser.add_argument("--dir", help="(Legacy) Working directory")
    parser.add_argument("--context", help="(Legacy) Context file path merged into prompt")

    args = parser.parse_args()

    if args.command is None and getattr(args, "provider", None) and getattr(args, "message", None):
        context_file, context_dir = _normalize_context_args(getattr(args, "context", None), getattr(args, "dir", None))
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
        status = check_provider_status()
        if args.format == "json":
            print(json.dumps({"type": "status", "timestamp": datetime.now().isoformat(), "providers": status}, indent=2))
        else:
            print("\n=== AI Provider Status ===\n")
            for provider, info in status.items():
                icon = "✓" if info["available"] else "✗"
                print(f"{icon} {provider}: {'Available' if info['available'] else 'Not found'}")
                if info["available"]:
                    print(f"  Path: {info['path']}")
                print(f"  {info['description']}\n")
        return

    if args.command == "tokens":
        token_info = check_token_usage()
        if args.format == "json":
            print(json.dumps({"type": "tokens", "timestamp": datetime.now().isoformat(), "providers": token_info}, indent=2))
        else:
            print("\n=== Token/Quota Status ===\n")
            for _provider, info in token_info.items():
                icon = "✓" if info.get("api_key_set") else "✗"
                print(f"{icon} {info['provider']}")
                print(f"  API Key: {'Set' if info.get('api_key_set') else 'Not set'}")
                print(f"  Note: {info['note']}")
                if info.get("check_method"):
                    print(f"  Check: {info['check_method']}")
                print()
        return

    if args.command not in {"run", "batch"}:
        parser.print_help()
        return

    context_file, context_dir = _normalize_context_args(getattr(args, "context", None), getattr(args, "dir", None))
    global_context_text = ""
    if context_file:
        global_context_text = load_context_text(context_file, args.context_encoding, args.context_max_chars)

    tasks: List[TaskRequest] = []

    if args.command == "run":
        if args.task_file:
            for i, t in enumerate(_read_task_file(args.task_file)):
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
                task = parse_task_spec(spec)
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
            for i, provider in enumerate(PROVIDERS.keys()):
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
            print("Error: Specify --provider/-m, --tasks, --task-file, or --all/-m", file=sys.stderr)
            sys.exit(2)

    if args.command == "batch":
        for i, t in enumerate(_read_task_file(args.file)):
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

    if not tasks:
        print("Error: No valid tasks to execute", file=sys.stderr)
        sys.exit(2)

    if args.resume and not args.progress:
        print("Error: --resume requires --progress", file=sys.stderr)
        sys.exit(2)

    if args.resume and args.progress:
        seen = _load_resume_ids(args.progress, resume_failed=args.resume_failed)
        tasks = [t for t in tasks if t.id not in seen]

    concurrency = args.concurrency if args.concurrency and args.concurrency > 0 else len(tasks)

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
        sys.exit(130)

    print_results(results, args.format)
    if args.output:
        _write_output_file(args.output, results, args.format)

    sys.exit(_exit_code_for_results(results, no_fail=args.no_fail))


if __name__ == "__main__":
    main()
