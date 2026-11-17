#!/usr/bin/env python3
"""Run an MSO PostToolUse hook and return Codex-compatible JSON on stdout."""

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = {
    "auditlog": [sys.executable, "auditlog.py"],
    "scaffold": ["bash", "scaffold-check.sh"],
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SCRIPTS:
        print("usage: posttooluse-json.py {auditlog|scaffold}", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    command = SCRIPTS[sys.argv[1]].copy()
    command[-1] = str(script_dir / command[-1])
    result = subprocess.run(command, input=sys.stdin.buffer.read(), capture_output=True)
    if result.stdout:
        sys.stderr.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    print(json.dumps({}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
