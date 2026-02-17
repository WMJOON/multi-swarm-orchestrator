from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def parse_task_spec(spec: str, allowed_providers: List[str]) -> TaskRequest:
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid task spec: {spec}. Format: provider:prompt[:id]")

    provider = parts[0].strip()
    prompt = parts[1].strip()
    task_id = parts[2].strip() if len(parts) > 2 else f"{provider}_{hash(prompt) % 10000}"

    if provider not in allowed_providers:
        raise ValueError(f"Unknown provider: {provider}. Available: {allowed_providers}")

    return TaskRequest(id=task_id, provider=provider, prompt=prompt)


def read_task_file(path: str) -> List[Dict[str, Any]]:
    if path == "-":
        task_data = json.loads(sys.stdin.read())
    else:
        with open(path, "r", encoding="utf-8") as f:
            task_data = json.load(f)
    if isinstance(task_data, list):
        return task_data
    return task_data.get("tasks", [])


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


def normalize_context_args(context_path: Optional[str], dir_path: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
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


def load_resume_ids(progress_path: str, *, resume_failed: bool) -> Dict[str, bool]:
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


def append_progress(progress_path: str, result: TaskResult) -> None:
    Path(progress_path).parent.mkdir(parents=True, exist_ok=True)
    with open(progress_path, "a", encoding="utf-8") as f:
        f.write(json_dumps(asdict(result)) + "\n")


def format_text_results(results: List[TaskResult]) -> str:
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
            print(json_dumps(asdict(r)))
        return

    print(format_text_results(results))


def write_output_file(path: str, results: List[TaskResult], fmt: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        p.write_text(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if fmt == "json-map":
        p.write_text(json.dumps({r.id: asdict(r) for r in results}, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if fmt == "jsonl":
        p.write_text("\n".join(json_dumps(asdict(r)) for r in results) + "\n", encoding="utf-8")
        return
    p.write_text(format_text_results(results), encoding="utf-8")


def exit_code_for_results(results: List[TaskResult], *, no_fail: bool) -> int:
    if no_fail:
        return 0
    return 0 if all(r.success for r in results) else 1
