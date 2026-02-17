#!/usr/bin/env python3
"""
Embed a context/PRD file into tasks.json prompts.

Primary use:
- Avoid shell arg-length / quoting issues by preparing tasks.json offline.
- Replace a placeholder token (default: {{CONTEXT}}) inside each prompt.

If a prompt doesn't include the placeholder, this script prepends the context using a template.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_TEMPLATE = "{context}\n\n---\n\n{prompt}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed PRD/context text into a tasks.json file")
    parser.add_argument("tasks_file", help="Input tasks.json (or a list JSON) path")
    parser.add_argument("--context", required=True, help="Context/PRD file path")
    parser.add_argument("--placeholder", default="{{CONTEXT}}", help="Placeholder token to replace in prompts")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Template for prompts without placeholder")
    parser.add_argument("--max-chars", type=int, default=None, help="Max chars to read from context (default: unlimited)")
    parser.add_argument("--inplace", action="store_true", help="Edit tasks_file in-place")
    parser.add_argument("--out", help="Output path (default: <tasks_file>.embedded.json)")
    args = parser.parse_args()

    tasks_path = Path(args.tasks_file)
    context_text = Path(args.context).read_text(encoding="utf-8")
    if args.max_chars is not None and args.max_chars >= 0 and len(context_text) > args.max_chars:
        context_text = context_text[: args.max_chars]

    data = read_json(tasks_path)
    tasks: List[Dict[str, Any]]
    wrapped = False
    if isinstance(data, dict):
        tasks = data.get("tasks", [])
        wrapped = True
    elif isinstance(data, list):
        tasks = data
    else:
        raise SystemExit("Invalid tasks JSON: expected object with 'tasks' or a list")

    for t in tasks:
        prompt = t.get("prompt", "")
        if args.placeholder in prompt:
            t["prompt"] = prompt.replace(args.placeholder, context_text)
        else:
            t["prompt"] = args.template.format(context=context_text, prompt=prompt)

    out_path = tasks_path if args.inplace else Path(args.out) if args.out else tasks_path.with_suffix(".embedded.json")
    write_json(out_path, {"tasks": tasks} if wrapped else tasks)


if __name__ == "__main__":
    main()

