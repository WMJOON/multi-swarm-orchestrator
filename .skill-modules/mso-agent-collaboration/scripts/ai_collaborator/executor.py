from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from .providers import (
    configured_models,
    discover_provider_models,
    find_executable,
    is_template_required,
    provider_command,
    provider_config,
    resolve_template,
    template_env_var,
)
from .utils import TaskRequest, TaskResult, append_progress, load_context_text, merge_prompt


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


async def _run_template_command(
    template: str,
    prompt: str,
    *,
    cwd: str,
    timeout: int,
) -> TaskResult:
    start = datetime.now()

    prompt_file = Path(tempfile.mkstemp(prefix="ai-collab-prompt-", suffix=".txt")[1])
    response_file = Path(tempfile.mkstemp(prefix="ai-collab-response-", suffix=".txt")[1])

    try:
        prompt_file.write_text(prompt, encoding="utf-8")
        cmd = template.replace("{PROMPT_FILE}", str(prompt_file)).replace("{RESPONSE_FILE}", str(response_file))

        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return TaskResult(
                id="template",
                provider="template",
                model=None,
                success=False,
                returncode=proc.returncode,
                timed_out=True,
                cancelled=False,
                output="",
                error=f"Template command timed out after {timeout} seconds",
                execution_time=(datetime.now() - start).total_seconds(),
                timestamp=start.isoformat(),
            )

        output = ""
        if response_file.exists():
            output = response_file.read_text(encoding="utf-8", errors="replace")
        if not output and stdout:
            output = stdout.decode(errors="replace")

        err = stderr.decode(errors="replace") if stderr else ""

        return TaskResult(
            id="template",
            provider="template",
            model=None,
            success=proc.returncode == 0,
            returncode=proc.returncode,
            timed_out=False,
            cancelled=False,
            output=output,
            error=err if proc.returncode != 0 else "",
            execution_time=(datetime.now() - start).total_seconds(),
            timestamp=start.isoformat(),
        )
    finally:
        try:
            prompt_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            response_file.unlink(missing_ok=True)
        except Exception:
            pass


def _model_help(provider: str, requested_model: Optional[str]) -> str:
    if not requested_model:
        return ""

    configured = configured_models(provider)
    discovered, discover_error = discover_provider_models(provider)
    candidates = list(dict.fromkeys(configured + discovered))

    if not candidates and not discover_error:
        return ""

    lines: List[str] = []
    lines.append(f"Requested model '{requested_model}' may be unavailable for provider '{provider}'.")
    if candidates:
        preview = ", ".join(candidates[:10])
        lines.append(f"Known models: {preview}")
    if discover_error:
        lines.append(f"Model discovery note: {discover_error}")
    lines.append(f"Hint: run `python3 scripts/collaborate.py models check --provider {provider}`")
    return "\n".join(lines)


async def run_ai_command_async(
    task: TaskRequest,
    *,
    global_context_text: str,
    context_template: str,
    context_encoding: str,
    context_max_chars: Optional[int],
) -> TaskResult:
    start = datetime.now()

    config = provider_config(task.provider)
    if not config:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            model=task.model,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"Provider '{task.provider}' not supported.",
            execution_time=0.0,
            timestamp=start.isoformat(),
        )

    executable = find_executable(task.provider)
    if not executable:
        return TaskResult(
            id=task.id,
            provider=task.provider,
            model=task.model,
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
                model=task.model,
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

    template_name, template = resolve_template(task.provider)

    if is_template_required(task.provider) and not template:
        required_hint = template_name or template_env_var(task.provider) or "AI_COLLABORATOR_<PROVIDER>_CMD_TEMPLATE"
        return TaskResult(
            id=task.id,
            provider=task.provider,
            model=task.model,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"{required_hint} is required for provider '{task.provider}'.",
            execution_time=(datetime.now() - start).total_seconds(),
            timestamp=start.isoformat(),
        )

    if template:
        templated = await _run_template_command(
            template,
            final_prompt,
            cwd=task.context_dir if task.context_dir else os.getcwd(),
            timeout=task.timeout,
        )
        return TaskResult(
            id=task.id,
            provider=task.provider,
            model=task.model,
            success=templated.success,
            returncode=templated.returncode,
            timed_out=templated.timed_out,
            cancelled=templated.cancelled,
            output=templated.output,
            error=templated.error,
            execution_time=templated.execution_time,
            timestamp=templated.timestamp,
        )

    full_cmd = provider_command(task.provider, executable, use_stdin=True, model=task.model)

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            cwd=task.context_dir if task.context_dir else os.getcwd(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=final_prompt.encode("utf-8")),
                timeout=task.timeout,
            )
            output = stdout.decode(errors="replace") if stdout else ""
            err = stderr.decode(errors="replace") if stderr else ""
            success = proc.returncode == 0

            if not success:
                model_help = _model_help(task.provider, task.model)
                if model_help:
                    err = (err + "\n\n" + model_help).strip()

            return TaskResult(
                id=task.id,
                provider=task.provider,
                model=task.model,
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
                model=task.model,
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
            model=task.model,
            success=False,
            returncode=None,
            timed_out=False,
            cancelled=False,
            output="",
            error=f"Unexpected error: {e}",
            execution_time=(datetime.now() - start).total_seconds(),
            timestamp=start.isoformat(),
        )


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
                append_progress(progress_path, res)
            return res

    coros = [runner(t) for t in tasks]
    return await asyncio.gather(*coros)
