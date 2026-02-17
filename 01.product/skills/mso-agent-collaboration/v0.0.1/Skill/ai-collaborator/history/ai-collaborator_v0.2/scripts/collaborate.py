#!/usr/bin/env python3
"""
AI Collaborator v0.2
- 비동기 동시 요청 처리 (async concurrent execution)
- 각 요청마다 다른 provider/prompt 지정 가능
- 토큰 잔량 체크 기능
- Grok 제거
"""

import subprocess
import argparse
import sys
import os
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict


# Provider configurations
PROVIDERS = {
    "codex": {
        "path": "/Users/wmjoon/.bun/bin/codex",
        "alt_paths": ["/opt/homebrew/bin/codex", "codex"],
        "cmd": ["exec", "--skip-git-repo-check"],
        "token_check_cmd": None,
        "description": "OpenAI Codex - Best for overall AX/AI strategy"
    },
    "claude": {
        "path": "/opt/homebrew/bin/claude",
        "alt_paths": ["claude"],
        "cmd": ["-p"],
        "token_check_cmd": None,
        "description": "Claude Code - High-performance coding assistant"
    },
    "gemini": {
        "path": "/opt/homebrew/bin/gemini",
        "alt_paths": ["gemini"],
        "cmd": [],
        "token_check_cmd": None,
        "description": "Gemini CLI - Strong in Google ecosystem"
    }
}


@dataclass
class TaskRequest:
    """Individual task request configuration."""
    id: str
    provider: str
    prompt: str
    context_dir: Optional[str] = None
    timeout: int = 300


@dataclass
class TaskResult:
    """Result of a single task execution."""
    id: str
    provider: str
    success: bool
    output: str
    error: str
    execution_time: float
    timestamp: str


def find_executable(provider: str) -> Optional[str]:
    """Find the executable path for a provider."""
    config = PROVIDERS.get(provider)
    if not config:
        return None

    if os.path.exists(config["path"]):
        return config["path"]

    for alt_path in config.get("alt_paths", []):
        if os.path.exists(alt_path):
            return alt_path
        try:
            result = subprocess.run(
                ["which", alt_path],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

    return None


def check_provider_status() -> Dict[str, Dict[str, Any]]:
    """Check availability status of all providers."""
    status = {}
    for provider, config in PROVIDERS.items():
        executable = find_executable(provider)
        status[provider] = {
            "available": executable is not None,
            "path": executable,
            "description": config["description"]
        }
    return status


async def run_ai_command_async(task: TaskRequest) -> TaskResult:
    """Run a single AI command asynchronously."""
    start_time = datetime.now()

    if task.provider not in PROVIDERS:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            output="",
            error=f"Provider '{task.provider}' not supported. Available: {list(PROVIDERS.keys())}",
            execution_time=0,
            timestamp=start_time.isoformat()
        )

    executable = find_executable(task.provider)
    if not executable:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            output="",
            error=f"{task.provider} CLI not found on system.",
            execution_time=0,
            timestamp=start_time.isoformat()
        )

    config = PROVIDERS[task.provider]
    full_cmd = [executable] + config["cmd"] + [task.prompt]

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            cwd=task.context_dir if task.context_dir else os.getcwd(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=task.timeout
            )

            return TaskResult(
                id=task.id,
                provider=task.provider,
                success=proc.returncode == 0,
                output=stdout.decode() if stdout else "",
                error=stderr.decode() if stderr and proc.returncode != 0 else "",
                execution_time=(datetime.now() - start_time).total_seconds(),
                timestamp=start_time.isoformat()
            )

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return TaskResult(
                id=task.id,
                provider=task.provider,
                success=False,
                output="",
                error=f"Command timed out after {task.timeout} seconds",
                execution_time=(datetime.now() - start_time).total_seconds(),
                timestamp=start_time.isoformat()
            )

    except Exception as e:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            success=False,
            output="",
            error=f"Unexpected error: {str(e)}",
            execution_time=(datetime.now() - start_time).total_seconds(),
            timestamp=start_time.isoformat()
        )


async def run_batch_async(tasks: List[TaskRequest]) -> Dict[str, TaskResult]:
    """Run multiple tasks concurrently using asyncio."""
    coroutines = [run_ai_command_async(task) for task in tasks]
    results = await asyncio.gather(*coroutines, return_exceptions=True)

    result_dict = {}
    for task, result in zip(tasks, results):
        if isinstance(result, Exception):
            result_dict[task.id] = TaskResult(
                id=task.id,
                provider=task.provider,
                success=False,
                output="",
                error=str(result),
                execution_time=0,
                timestamp=datetime.now().isoformat()
            )
        else:
            result_dict[task.id] = result

    return result_dict


def run_ai_command(
    provider: str,
    prompt: str,
    context_dir: Optional[str] = None,
    timeout: int = 300
) -> Dict[str, Any]:
    """Synchronous wrapper for single command execution."""
    task = TaskRequest(
        id=f"{provider}_0",
        provider=provider,
        prompt=prompt,
        context_dir=context_dir,
        timeout=timeout
    )
    result = asyncio.run(run_ai_command_async(task))
    return asdict(result)


def run_batch(tasks: List[TaskRequest]) -> Dict[str, Dict[str, Any]]:
    """Synchronous wrapper for batch execution."""
    results = asyncio.run(run_batch_async(tasks))
    return {k: asdict(v) for k, v in results.items()}


def parse_task_spec(spec: str) -> TaskRequest:
    """
    Parse a task specification string.
    Format: provider:prompt or provider:prompt:id
    Example: "claude:Review this code" or "gemini:Analyze performance:task1"
    """
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid task spec: {spec}. Format: provider:prompt[:id]")

    provider = parts[0].strip()
    prompt = parts[1].strip()
    task_id = parts[2].strip() if len(parts) > 2 else f"{provider}_{hash(prompt) % 10000}"

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDERS.keys())}")

    return TaskRequest(id=task_id, provider=provider, prompt=prompt)


def check_token_usage() -> Dict[str, Dict[str, Any]]:
    """Check token/quota status for each provider."""
    token_info = {}

    openai_key = os.environ.get("OPENAI_API_KEY")
    token_info["codex"] = {
        "provider": "OpenAI (Codex)",
        "api_key_set": bool(openai_key),
        "note": "Check usage at https://platform.openai.com/usage" if openai_key else "OPENAI_API_KEY not found",
        "check_method": "API dashboard" if openai_key else None
    }

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    token_info["claude"] = {
        "provider": "Anthropic (Claude)",
        "api_key_set": bool(anthropic_key),
        "note": "Check usage at https://console.anthropic.com/settings/usage" if anthropic_key else "ANTHROPIC_API_KEY not found",
        "check_method": "API dashboard" if anthropic_key else None
    }

    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    token_info["gemini"] = {
        "provider": "Google (Gemini)",
        "api_key_set": bool(google_key),
        "note": "Check usage at https://aistudio.google.com/apikey" if google_key else "GOOGLE_API_KEY or GEMINI_API_KEY not found",
        "check_method": "Google AI Studio" if google_key else None
    }

    return token_info


def print_results(results: Dict[str, Any], format: str = "text"):
    """Print results in specified format."""
    if format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 60)
    print("AI COLLABORATOR RESULTS")
    print("=" * 60)

    for task_id, result in results.items():
        print(f"\n--- [{task_id}] {result.get('provider', 'unknown').upper()} ---")
        print(f"Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"Execution Time: {result.get('execution_time', 0):.2f}s")

        if result.get("output"):
            print(f"\nOutput:\n{result['output']}")

        if result.get("error"):
            print(f"\nError:\n{result['error']}")

        print("-" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="AI Collaborator v0.2 - Async multi-provider execution with individual task control"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run AI command(s)")
    run_parser.add_argument(
        "--provider", "-p",
        choices=list(PROVIDERS.keys()),
        help="Single provider to use (with --message)"
    )
    run_parser.add_argument(
        "--message", "-m",
        help="Prompt message for single provider mode"
    )
    run_parser.add_argument(
        "--tasks", "-T",
        nargs="+",
        help="Multiple task specs: 'provider:prompt[:id]' (e.g., 'claude:Review code' 'gemini:Check perf:perf_check')"
    )
    run_parser.add_argument(
        "--task-file",
        help="JSON file with task definitions"
    )
    run_parser.add_argument(
        "--all",
        action="store_true",
        help="Run --message on all available providers"
    )
    run_parser.add_argument(
        "--dir", "-d",
        help="Working directory for commands"
    )
    run_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=300,
        help="Timeout per task in seconds (default: 300)"
    )
    run_parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # Batch command (alternative syntax)
    batch_parser = subparsers.add_parser("batch", help="Run batch from JSON file")
    batch_parser.add_argument(
        "file",
        help="JSON file with task definitions"
    )
    batch_parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Check provider availability")
    status_parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text"
    )

    # Token command
    token_parser = subparsers.add_parser("tokens", help="Check token/quota status")
    token_parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text"
    )

    # Legacy support
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), help="(Legacy) AI Provider")
    parser.add_argument("--message", help="(Legacy) Prompt message")
    parser.add_argument("--dir", help="(Legacy) Working directory")

    args = parser.parse_args()

    # Handle legacy mode
    if args.command is None and hasattr(args, 'provider') and args.provider and hasattr(args, 'message') and args.message:
        result = run_ai_command(args.provider, args.message, getattr(args, 'dir', None))
        if result["success"]:
            print(result["output"])
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        return

    # Handle commands
    if args.command == "run":
        tasks = []

        # Option 1: Task file
        if args.task_file:
            with open(args.task_file, 'r') as f:
                task_data = json.load(f)
            for i, t in enumerate(task_data.get("tasks", task_data)):
                tasks.append(TaskRequest(
                    id=t.get("id", f"task_{i}"),
                    provider=t["provider"],
                    prompt=t["prompt"],
                    context_dir=t.get("context_dir", args.dir),
                    timeout=t.get("timeout", args.timeout)
                ))

        # Option 2: Inline task specs
        elif args.tasks:
            for spec in args.tasks:
                task = parse_task_spec(spec)
                task.context_dir = args.dir
                task.timeout = args.timeout
                tasks.append(task)

        # Option 3: Single provider with message
        elif args.provider and args.message:
            tasks.append(TaskRequest(
                id=f"{args.provider}_0",
                provider=args.provider,
                prompt=args.message,
                context_dir=args.dir,
                timeout=args.timeout
            ))

        # Option 4: All providers with same message
        elif args.all and args.message:
            for i, provider in enumerate(PROVIDERS.keys()):
                if find_executable(provider):
                    tasks.append(TaskRequest(
                        id=f"{provider}_{i}",
                        provider=provider,
                        prompt=args.message,
                        context_dir=args.dir,
                        timeout=args.timeout
                    ))

        else:
            print("Error: Specify --provider/-m, --tasks, --task-file, or --all/-m", file=sys.stderr)
            sys.exit(1)

        if not tasks:
            print("Error: No valid tasks to execute", file=sys.stderr)
            sys.exit(1)

        print(f"Executing {len(tasks)} task(s) asynchronously...\n")
        results = run_batch(tasks)
        print_results(results, args.format)

    elif args.command == "batch":
        with open(args.file, 'r') as f:
            task_data = json.load(f)

        tasks = []
        for i, t in enumerate(task_data.get("tasks", task_data)):
            tasks.append(TaskRequest(
                id=t.get("id", f"task_{i}"),
                provider=t["provider"],
                prompt=t["prompt"],
                context_dir=t.get("context_dir"),
                timeout=t.get("timeout", 300)
            ))

        print(f"Executing {len(tasks)} task(s) from batch file...\n")
        results = run_batch(tasks)
        print_results(results, args.format)

    elif args.command == "status":
        status = check_provider_status()
        if args.format == "json":
            print(json.dumps(status, indent=2))
        else:
            print("\n=== AI Provider Status ===\n")
            for provider, info in status.items():
                icon = "✓" if info["available"] else "✗"
                print(f"{icon} {provider}: {'Available' if info['available'] else 'Not found'}")
                if info["available"]:
                    print(f"  Path: {info['path']}")
                print(f"  {info['description']}")
                print()

    elif args.command == "tokens":
        token_info = check_token_usage()
        if args.format == "json":
            print(json.dumps(token_info, indent=2))
        else:
            print("\n=== Token/Quota Status ===\n")
            for provider, info in token_info.items():
                icon = "✓" if info.get("api_key_set") else "✗"
                print(f"{icon} {info['provider']}")
                print(f"  API Key: {'Set' if info.get('api_key_set') else 'Not set'}")
                print(f"  Note: {info['note']}")
                if info.get("check_method"):
                    print(f"  Check: {info['check_method']}")
                print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
