#!/usr/bin/env python3
"""
setup.py — mso-agent-audit-log 환경 초기화.
audit DB 생성 + 워크로그 디렉터리 생성 + 세션 훅 주입을 한 번에 수행한다.
"""
import argparse
import sys
from pathlib import Path

# 스크립트 디렉터리 기준으로 동일 패키지 임포트
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from init_db import ensure_db, resolve_audit_db_path  # noqa: E402
from inject_hooks import inject  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(
        description="mso-agent-audit-log 환경 초기화 (DB + 훅)"
    )
    p.add_argument("--project-root", required=True, help="프로젝트 루트 디렉터리")
    p.add_argument(
        "--worklog-dir",
        help="워크로그 디렉터리 (기본: {project-root}/00.agent_log/logs)",
    )
    p.add_argument(
        "--db",
        help="audit DB 경로 (기본: {project-root}/.mso-context/audit_global.db)",
    )
    p.add_argument("--schema-version", default="1.5.0")
    p.add_argument(
        "--target",
        choices=["claude", "codex", "all"],
        default="all",
        help="훅 주입 대상 (기본: all)",
    )
    p.add_argument("--dry-run", action="store_true", help="실제 변경 없이 결과만 출력")
    args = p.parse_args()

    project_root = Path(args.project_root).resolve()
    worklog_dir = Path(args.worklog_dir) if args.worklog_dir else project_root / "00.agent_log" / "logs"
    db_path = Path(args.db).resolve() if args.db else project_root / ".mso-context" / "audit_global.db"
    settings_path = project_root / ".claude" / "settings.json"

    print(f"[mso-agent-audit-log setup]")
    print(f"  project-root : {project_root}")
    print(f"  audit DB     : {db_path}")
    print(f"  worklog-dir  : {worklog_dir}")
    print(f"  settings     : {settings_path}")
    print()

    # 1. 워크로그 디렉터리 생성
    if args.dry_run:
        print(f"[dry-run] mkdir {worklog_dir}")
    else:
        worklog_dir.mkdir(parents=True, exist_ok=True)
        print(f"worklog-dir  : {worklog_dir}  (ready)")

    # 2. audit DB 초기화
    if args.dry_run:
        print(f"[dry-run] init DB {db_path}  schema={args.schema_version}")
    else:
        ensure_db(db_path, args.schema_version, run_migrate=True)
        print(f"audit DB     : {db_path}  (ready)")

    # 3. 세션 훅 주입
    inject(settings_path, str(worklog_dir), dry_run=args.dry_run, target=args.target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
