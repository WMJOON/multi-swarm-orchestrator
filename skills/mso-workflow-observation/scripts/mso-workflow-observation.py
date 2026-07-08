#!/usr/bin/env python3
"""Workflow graph observation alias for mso-graph-observability."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    script = (
        Path(__file__).resolve().parents[2]
        / "mso-graph-observability"
        / "scripts"
        / "observe_graph.py"
    )
    sys.argv = [str(script), *sys.argv[1:]]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
