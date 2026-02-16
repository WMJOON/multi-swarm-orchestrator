from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import bus
from .executor import run_ai_command_async
from .providers import provider_names
from .schemas import validate_bus_message, validate_payload_by_type, validate_run_manifest
from .utils import DEFAULT_CONTEXT_TEMPLATE, TaskRequest

SKILL_ROOT = Path(__file__).resolve().parents[2]
SWARM_HISTORY_DIR = SKILL_ROOT / "history" / "swarm"
SYSTEM_RULES_TEXT = "swarm-bus;lease-retry-dead;collaborate-first-explicit-swarm"


def parse_agents_spec(spec: str) -> List[Tuple[str, str]]:
    """
    Parse: "planner:claude,coder:codex,reviewer:antigravity"
    """
    pairs: List[Tuple[str, str]] = []
    if not spec.strip():
        raise ValueError("--agents cannot be empty")

    allowed = set(provider_names())
    for token in [p.strip() for p in spec.split(",") if p.strip()]:
        if ":" not in token:
            raise ValueError(f"Invalid agent mapping: {token}. Expected agent:provider")
        agent, provider = token.split(":", 1)
        agent = agent.strip()
        provider = provider.strip()
        if not agent or not provider:
            raise ValueError(f"Invalid agent mapping: {token}")
        if provider not in allowed:
            raise ValueError(f"Unknown provider '{provider}'. Allowed: {sorted(allowed)}")
        pairs.append((agent, provider))
    return pairs


def _collaborate_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "collaborate.py"


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _trace_run_id(trace_id: str, rows: List[Dict[str, Any]]) -> str:
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, dict):
            run_id = payload.get("run_id")
            if isinstance(run_id, str) and run_id.startswith("run-"):
                return run_id
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:6]
    return f"run-{day}-{suffix}"


def _record_trace_manifest(db_path: str, trace_id: str, strict_schema: bool) -> None:
    rows = bus.messages_for_trace(db_path, trace_id)
    if not rows:
        return

    task_rows: Dict[str, Dict[str, Any]] = {}
    request_id_to_task_id: Dict[str, str] = {}

    role_allowlist = {"planner", "worker", "reviewer", "merge_agent"}
    task_counter = 0

    for row in rows:
        if row.get("type") != "TASK_REQUEST":
            continue

        task_counter += 1
        payload = row.get("payload")
        payload_obj = payload if isinstance(payload, dict) else {}

        task_id = payload_obj.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            task_id = f"task-{task_counter:03d}"

        request_id_to_task_id[row["id"]] = task_id

        status = "pending"
        if row.get("status") == "leased":
            status = "in_progress"
        elif row.get("status") == "dead":
            status = "failure"
        elif row.get("status") == "done":
            status = "in_progress"

        task_item: Dict[str, Any] = {
            "task_id": task_id,
            "owner_agent": row.get("to_agent", ""),
            "status": status,
            "exit_code": "S-001",
        }

        role = payload_obj.get("role")
        if isinstance(role, str) and role in role_allowlist:
            task_item["role"] = role

        depends_on = payload_obj.get("depends_on")
        if isinstance(depends_on, list) and all(isinstance(item, str) for item in depends_on):
            task_item["depends_on"] = depends_on

        task_rows[task_id] = task_item

    for row in rows:
        payload = row.get("payload")
        payload_obj = payload if isinstance(payload, dict) else {}
        msg_type = row.get("type")

        if msg_type == "TASK_RESULT":
            task_id = payload_obj.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                continue
            task = task_rows.setdefault(
                task_id,
                {"task_id": task_id, "owner_agent": row.get("from_agent", ""), "status": "pending", "exit_code": "S-001"},
            )
            task["status"] = "success"
            task["exit_code"] = payload_obj.get("exit_code", "E-000")

        if msg_type == "TASK_ERROR":
            message_id = payload_obj.get("message_id")
            task_id = None
            if isinstance(message_id, str):
                task_id = request_id_to_task_id.get(message_id)
            if not task_id:
                maybe_task = payload_obj.get("task_id")
                if isinstance(maybe_task, str) and maybe_task:
                    task_id = maybe_task
            if not task_id:
                continue

            task = task_rows.setdefault(
                task_id,
                {"task_id": task_id, "owner_agent": row.get("from_agent", ""), "status": "pending", "exit_code": "S-001"},
            )
            task["status"] = "failure"
            task["exit_code"] = "S-001"

        if msg_type == "TASK_UPDATE":
            message_id = payload_obj.get("message_id")
            if not isinstance(message_id, str):
                continue
            task_id = request_id_to_task_id.get(message_id)
            if not task_id:
                continue
            task = task_rows.get(task_id)
            if task:
                task["status"] = "in_progress"

    tasks = list(task_rows.values())

    status_values = {task.get("status") for task in tasks}
    if tasks and status_values == {"success"}:
        run_status = "completed"
    elif "failure" in status_values or "timeout" in status_values or "blocked" in status_values:
        run_status = "failed"
    elif "in_progress" in status_values:
        run_status = "in_progress"
    else:
        run_status = "pending"

    created_candidates = [_parse_iso(r.get("created_at")) for r in rows]
    updated_candidates = [_parse_iso(r.get("updated_at")) for r in rows]
    created = min((d for d in created_candidates if d is not None), default=datetime.now(timezone.utc))
    updated = max((d for d in updated_candidates if d is not None), default=created)

    retry_total = sum(
        1
        for r in rows
        if r.get("type") == "TASK_UPDATE"
        and isinstance(r.get("payload"), dict)
        and r["payload"].get("status") == "retry"
    )

    manifest = {
        "run_id": _trace_run_id(trace_id, rows),
        "created_at": created.isoformat(),
        "completed_at": updated.isoformat() if run_status in {"completed", "failed", "aborted"} else None,
        "status": run_status,
        "tasks": tasks,
        "config_hash": _sha256_prefixed(json.dumps({"trace_id": trace_id, "db_path": db_path}, sort_keys=True)),
        "system_rules_hash": _sha256_prefixed(SYSTEM_RULES_TEXT),
        "aggregate_metrics": {
            "total_tasks": len(tasks),
            "succeeded": sum(1 for t in tasks if t.get("status") == "success"),
            "failed": sum(1 for t in tasks if t.get("status") in {"failure", "timeout", "blocked"}),
            "total_duration_seconds": max(0.0, (updated - created).total_seconds()),
            "total_tokens": 0,
            "retry_total": retry_total,
            "conflict_count": 0,
        },
    }

    warnings = validate_run_manifest(manifest, strict=strict_schema)
    for warning in warnings:
        print(f"[warn] run manifest schema: {warning}")

    SWARM_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    safe_trace_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in trace_id)
    out_path = SWARM_HISTORY_DIR / f"{safe_trace_id}.run-manifest.json"
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def start_swarm_session(
    *,
    db_path: str,
    session: str,
    agents_spec: str,
    strict_schema: bool,
    poll_seconds: float,
    lease_seconds: int,
    max_attempts: int,
    inspect_interval: int,
) -> None:
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is required for swarm start")

    mappings = parse_agents_spec(agents_spec)

    script = _collaborate_script_path()
    py = Path(shutil.which("python3") or "python3")

    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode != 0:
        monitor_cmd = (
            f"{shlex.quote(str(py))} {shlex.quote(str(script))} "
            f"swarm inspect --db {shlex.quote(db_path)} --interval {inspect_interval}"
        )
        subprocess.run(["tmux", "new-session", "-d", "-s", session, "-n", "monitor", monitor_cmd], check=True)

    for agent, provider in mappings:
        existing = subprocess.run(
            ["tmux", "list-windows", "-t", session, "-F", "#W"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        if agent in existing:
            continue

        worker_cmd = (
            f"{shlex.quote(str(py))} {shlex.quote(str(script))} "
            f"swarm worker --db {shlex.quote(db_path)} "
            f"--agent {shlex.quote(agent)} --provider {shlex.quote(provider)} "
            f"--poll-seconds {poll_seconds} --lease-seconds {lease_seconds} --max-attempts {max_attempts}"
        )
        if strict_schema:
            worker_cmd += " --strict-schema"

        subprocess.run(["tmux", "new-window", "-t", f"{session}:", "-n", agent, worker_cmd], check=True)

    print(f"started swarm session: {session}")
    print(f"attach with: tmux attach -t {session}")


def stop_swarm_session(session: str) -> None:
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is required for swarm stop")
    subprocess.run(["tmux", "kill-session", "-t", session], check=True)
    print(f"stopped swarm session: {session}")


def send_swarm_message(
    *,
    db_path: str,
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload_raw: str,
    trace_id: str | None,
    thread_id: str | None,
    strict_schema: bool,
) -> str:
    payload_obj = json.loads(payload_raw)

    validate_payload_by_type(msg_type, payload_obj, strict=strict_schema)

    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    trace = trace_id or f"tr_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    thread = thread_id or "th_default"

    envelope = {
        "id": "pending",
        "trace_id": trace,
        "thread_id": thread,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "type": msg_type,
        "payload": payload_obj,
        "status": "queued",
        "attempt": 0,
        "created_at": now,
        "updated_at": now,
    }
    validate_bus_message(envelope, strict=strict_schema)

    message_id = bus.send_message(
        db_path,
        from_agent=from_agent,
        to_agent=to_agent,
        msg_type=msg_type,
        payload=payload_obj,
        trace_id=trace,
        thread_id=thread,
    )
    _record_trace_manifest(db_path, trace, strict_schema=strict_schema)

    print(message_id)
    return message_id


def inspect_swarm(db_path: str, interval: int) -> None:
    interval = max(1, interval)
    while True:
        print("\033c", end="")
        print(f"db: {db_path}")
        print(f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        counts = bus.status_counts(db_path)
        print("status counts")
        print("-------------")
        if counts:
            for status, count in counts:
                print(f"{status:>8} : {count}")
        else:
            print("(no messages)")

        print("\nrecent messages")
        print("---------------")
        rows = bus.recent_messages(db_path, limit=20)
        if rows:
            for row in rows:
                print(
                    f"{row['created_at']}  {row['id'][:12]}  {row['type']:<12} "
                    f"{row['status']:<6} {row['from_agent']}->{row['to_agent']} a={row['attempt']}"
                )
        else:
            print("(empty)")

        time.sleep(interval)


def _derive_task_prompt(message: Dict[str, Any]) -> str:
    payload = message.get("payload")
    if isinstance(payload, dict):
        if payload.get("objective"):
            return str(payload["objective"])
        if payload.get("goal"):
            return str(payload["goal"])
        if payload.get("summary"):
            return str(payload["summary"])
    return json.dumps(payload, ensure_ascii=False)


def _derive_run_id(message: Dict[str, Any]) -> str:
    payload = message.get("payload")
    if isinstance(payload, dict):
        rid = payload.get("run_id")
        if isinstance(rid, str) and rid.startswith("run-"):
            return rid
    return f"run-{datetime.now().strftime('%Y%m%d')}-{message['id'][:6]}"


def _derive_task_id(message: Dict[str, Any]) -> str:
    payload = message.get("payload")
    if isinstance(payload, dict):
        tid = payload.get("task_id")
        if isinstance(tid, str) and tid.startswith("task-"):
            return tid
    return f"task-{abs(hash(message['id'])) % 1000:03d}"


def _build_output_report_payload(message: Dict[str, Any], result_output: str, success: bool, error_text: str) -> Dict[str, Any]:
    summary = (result_output or error_text or "No output")[:2000]
    if len(summary) < 10:
        summary = (summary + " (no detailed output)").strip()

    if success:
        status = "success"
        exit_code = "E-000"
        next_action = "proceed"
    else:
        status = "failure"
        exit_code = "S-001"
        next_action = "retry"

    return {
        "run_id": _derive_run_id(message),
        "task_id": _derive_task_id(message),
        "status": status,
        "exit_code": exit_code,
        "changed_files": [],
        "summary": summary,
        "next_action": next_action,
    }


def _send(
    db_path: str,
    *,
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: Dict[str, Any],
    trace_id: str,
    thread_id: str,
    strict_schema: bool,
) -> str:
    validate_payload_by_type(msg_type, payload, strict=strict_schema)
    return bus.send_message(
        db_path,
        from_agent=from_agent,
        to_agent=to_agent,
        msg_type=msg_type,
        payload=payload,
        trace_id=trace_id,
        thread_id=thread_id,
    )


def run_worker_loop(
    *,
    db_path: str,
    agent: str,
    provider: str,
    strict_schema: bool,
    poll_seconds: float,
    lease_seconds: int,
    max_attempts: int,
    task_timeout: int,
) -> None:
    worker_id = f"{agent}-{int(time.time())}"
    print(f"worker started: agent={agent} provider={provider} worker_id={worker_id}")

    while True:
        msg = bus.claim_next_message(
            db_path,
            to_agent=agent,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if msg is None:
            time.sleep(max(0.1, poll_seconds))
            continue

        msg_id = msg["id"]
        msg_type = msg["type"]
        trace_id = msg["trace_id"]
        thread_id = msg["thread_id"]
        from_agent = msg["from_agent"]
        attempt = int(msg.get("attempt", 1))

        print(f"[{agent}] handling id={msg_id} type={msg_type} from={from_agent} attempt={attempt}")

        if msg_type == "PING":
            pong_payload = {"reply_to": msg_id, "worker": worker_id}
            _send(
                db_path,
                from_agent=agent,
                to_agent=from_agent,
                msg_type="PONG",
                payload=pong_payload,
                trace_id=trace_id,
                thread_id=thread_id,
                strict_schema=strict_schema,
            )
            bus.mark_done(db_path, msg_id)
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
            continue

        if msg_type in {"TASK_ACCEPT", "TASK_UPDATE", "TASK_RESULT", "TASK_ERROR", "PONG"}:
            bus.mark_done(db_path, msg_id)
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
            continue

        if msg_type != "TASK_REQUEST":
            err_text = f"unsupported message type: {msg_type}"
            bus.mark_dead(db_path, msg_id, err_text)
            _send(
                db_path,
                from_agent=agent,
                to_agent=from_agent,
                msg_type="TASK_ERROR",
                payload={"message_id": msg_id, "worker": worker_id, "error": err_text},
                trace_id=trace_id,
                thread_id=thread_id,
                strict_schema=False,
            )
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
            continue

        warnings = validate_payload_by_type("TASK_REQUEST", msg.get("payload"), strict=strict_schema)
        for w in warnings:
            print(f"[warn] TASK_REQUEST schema: {w}")

        accept_payload = {
            "accepted": True,
            "message_id": msg_id,
            "worker": worker_id,
            "provider": provider,
        }
        _send(
            db_path,
            from_agent=agent,
            to_agent=from_agent,
            msg_type="TASK_ACCEPT",
            payload=accept_payload,
            trace_id=trace_id,
            thread_id=thread_id,
            strict_schema=False,
        )

        task = TaskRequest(
            id=msg_id,
            provider=provider,
            prompt=_derive_task_prompt(msg),
            context_dir=None,
            timeout=task_timeout,
        )

        result = asyncio.run(
            run_ai_command_async(
                task,
                global_context_text="",
                context_template=DEFAULT_CONTEXT_TEMPLATE,
                context_encoding="utf-8",
                context_max_chars=None,
            )
        )

        if result.success:
            result_payload = _build_output_report_payload(msg, result.output, True, "")
            warnings = validate_payload_by_type("TASK_RESULT", result_payload, strict=strict_schema)
            for w in warnings:
                print(f"[warn] TASK_RESULT schema: {w}")

            _send(
                db_path,
                from_agent=agent,
                to_agent=from_agent,
                msg_type="TASK_RESULT",
                payload=result_payload,
                trace_id=trace_id,
                thread_id=thread_id,
                strict_schema=False,
            )
            bus.mark_done(db_path, msg_id)
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
            continue

        err_text = result.error or "provider execution failed"
        if attempt >= max_attempts:
            bus.mark_dead(db_path, msg_id, err_text)
            _send(
                db_path,
                from_agent=agent,
                to_agent=from_agent,
                msg_type="TASK_ERROR",
                payload={"message_id": msg_id, "worker": worker_id, "error": err_text},
                trace_id=trace_id,
                thread_id=thread_id,
                strict_schema=False,
            )
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
        else:
            bus.mark_retry(db_path, msg_id, err_text)
            _send(
                db_path,
                from_agent=agent,
                to_agent=from_agent,
                msg_type="TASK_UPDATE",
                payload={"message_id": msg_id, "worker": worker_id, "status": "retry", "attempt": attempt},
                trace_id=trace_id,
                thread_id=thread_id,
                strict_schema=False,
            )
            _record_trace_manifest(db_path, trace_id, strict_schema=strict_schema)
