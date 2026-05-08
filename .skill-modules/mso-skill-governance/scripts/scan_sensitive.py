#!/usr/bin/env python3
"""Sensitive data scanner for MSO skill pack and related vaults.

Detects:
  - Hardcoded personal paths  (/Users/<name>/...)
  - API keys                  (OpenAI sk-*, Google AIza*, Anthropic)
  - Hardcoded secrets         (api_key/token/password = "...")
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# ──────────────────────────────────────────────
# 탐지 패턴
# ──────────────────────────────────────────────
PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "personal_path",
        # /Users/<name>/... 형태. /opt/, /usr/ 등 시스템 경로는 이 패턴에 해당 안 됨
        "regex": re.compile(r"/Users/([A-Za-z][A-Za-z0-9_.-]{2,})/"),
        "severity": "fail",
        "description": "개인 사용자 경로 하드코딩",
    },
    {
        "name": "anthropic_api_key",
        # anthropic을 openai보다 먼저 — sk-ant-* 가 sk-* 에도 걸리므로 우선 처리
        "regex": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
        "severity": "fail",
        "description": "Anthropic API 키",
    },
    {
        "name": "openai_api_key",
        # sk-ant-* 는 위에서 이미 처리되므로 negative lookahead로 제외
        "regex": re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}"),
        "severity": "fail",
        "description": "OpenAI API 키",
    },
    {
        "name": "google_api_key",
        # Google API 키는 AIza + 36자 = 40자. \b 대신 negative lookahead 사용
        "regex": re.compile(r"AIza[0-9A-Za-z_-]{35,}(?![0-9A-Za-z_-])"),
        "severity": "fail",
        "description": "Google API 키",
    },
    {
        "name": "hardcoded_secret",
        "regex": re.compile(
            r'(?:api_key|secret_key|access_token|auth_token|password)\s*[:=]\s*["\']([A-Za-z0-9/+_-]{16,})["\']',
            re.IGNORECASE,
        ),
        "severity": "fail",
        "description": "하드코딩된 시크릿 값",
    },
]

# 허용 문자열 (이 문자열이 같은 줄에 있으면 false positive로 건너뜀)
LINE_ALLOWLIST = [
    "os.path.expanduser",
    "os.environ",
    "os.getenv",
    "${HOME}",
    "expanduser(",
    "YOUR_KEY",
    "<YOUR",
    "placeholder",
    "example",
    "# ",          # 주석 전용 줄
    "env_var",
    "model_env_vars",
]

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "history"}
SKIP_EXTS = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".db", ".sqlite"}


def _is_allowed_line(line: str) -> bool:
    lower = line.lower()
    return any(a.lower() in lower for a in LINE_ALLOWLIST)


def _is_personal_path_hit(match: re.Match, line: str) -> bool:
    """/Users/<name>/... 매치는 항상 개인 경로. 시스템 경로는 이 regex에 걸리지 않음."""
    return True


def scan_file(path: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if path.suffix.lower() in SKIP_EXTS:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for lineno, line in enumerate(text.splitlines(), 1):
        if _is_allowed_line(line):
            continue
        for pat in PATTERNS:
            for m in pat["regex"].finditer(line):
                if pat["name"] == "personal_path" and not _is_personal_path_hit(m, line):
                    continue
                excerpt = line.strip()[:120]
                findings.append(
                    {
                        "file": str(path),
                        "line": lineno,
                        "pattern": pat["name"],
                        "severity": pat["severity"],
                        "description": pat["description"],
                        "excerpt": excerpt,
                    }
                )
                break  # 한 줄에 같은 패턴 중복 방지
    return findings


def scan_dir(root: Path, extensions: List[str] | None = None) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        findings.extend(scan_file(path))
    return findings


def main() -> int:
    p = argparse.ArgumentParser(description="Sensitive data scanner")
    p.add_argument("paths", nargs="*", help="파일 또는 디렉토리 경로 (기본: MSO repo root)")
    p.add_argument("--ext", nargs="*", default=None, help="스캔할 확장자 (예: .py .yaml .md)")
    p.add_argument("--json", dest="json_out", action="store_true", help="JSON 출력")
    p.add_argument("--fail-on-warn", action="store_true", help="warn도 exit code 1로 처리")
    args = p.parse_args()

    if args.paths:
        targets = [Path(t).expanduser().resolve() for t in args.paths]
    else:
        targets = [Path(__file__).resolve().parents[3]]

    all_findings: List[Dict[str, Any]] = []
    for target in targets:
        if target.is_file():
            all_findings.extend(scan_file(target))
        elif target.is_dir():
            all_findings.extend(scan_dir(target, args.ext))

    if args.json_out:
        print(json.dumps({"findings": all_findings, "total": len(all_findings)}, ensure_ascii=False, indent=2))
    else:
        if all_findings:
            print(f"[scan_sensitive] {len(all_findings)}건 감지")
            for f in all_findings:
                severity_tag = f"[{f['severity'].upper()}]"
                print(f"  {severity_tag} {f['file']}:{f['line']} — {f['description']}")
                print(f"         {f['excerpt']}")
        else:
            print("[scan_sensitive] 이상 없음")

    fail_count = sum(1 for f in all_findings if f["severity"] == "fail")
    warn_count = sum(1 for f in all_findings if f["severity"] == "warn")

    if fail_count > 0:
        return 1
    if args.fail_on_warn and warn_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
