#!/usr/bin/env python3
"""MSO 글로벌 레지스트리 초기화 스크립트.

~/.mso-registry/ 디렉토리 구조를 생성하고 seed directive를 복사한다.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# 글로벌 레지스트리 루트
REGISTRY_ROOT = Path.home() / ".mso-registry"

# seed 소스 경로
SEED_BASE = Path(__file__).resolve().parent.parent / "directives"

# 초기 도메인 목록
SEED_DOMAINS = ["analysis", "general"]


def create_registry_config(force: bool = False) -> None:
    """registry_config.json 생성. force=True면 덮어쓰기."""
    meta_dir = REGISTRY_ROOT / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    config_path = meta_dir / "registry_config.json"
    if config_path.exists() and not force:
        print(f"[SKIP] 이미 존재: {config_path}")
        return

    config = {
        "version": "0.1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolution_order": ["global", "workspace", "seed"],
        "merge_strategy": "union_global_priority",
        "domains": list(SEED_DOMAINS),
    }

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[CREATE] {config_path}")


def copy_seed_domain(domain: str, force: bool = False) -> int:
    """seed 도메인 디렉토리를 글로벌 레지스트리로 복사. 복사된 파일 수 반환."""
    src = SEED_BASE / domain
    dst = REGISTRY_ROOT / domain

    if not src.exists():
        print(f"[ERROR] seed 소스 없음: {src}", file=sys.stderr)
        sys.exit(1)

    dst.mkdir(parents=True, exist_ok=True)
    copied = 0

    for src_file in src.rglob("*"):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        if dst_file.exists() and not force:
            print(f"[SKIP] 이미 존재: {dst_file}")
            continue

        shutil.copy2(src_file, dst_file)
        copied += 1
        print(f"[COPY] {rel} -> {dst_file}")

    return copied


def init_registry(force: bool = False) -> None:
    """글로벌 레지스트리 초기화 메인 로직."""
    print(f"=== MSO 글로벌 레지스트리 초기화 ===")
    print(f"대상: {REGISTRY_ROOT}")
    print(f"모드: {'강제 덮어쓰기' if force else '머지 (기존 보존)'}")
    print()

    # 1. 레지스트리 루트 생성
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)

    # 2. workflows 빈 디렉토리 생성
    workflows_dir = REGISTRY_ROOT / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    print(f"[DIR] {workflows_dir}")

    # 3. registry_config.json 생성
    create_registry_config(force)

    # 4. seed 도메인 복사
    total_copied = 0
    for domain in SEED_DOMAINS:
        print(f"\n--- 도메인: {domain} ---")
        total_copied += copy_seed_domain(domain, force)

    print(f"\n=== 완료: {total_copied}개 파일 복사됨 ===")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MSO 글로벌 레지스트리 초기화"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 파일 강제 덮어쓰기",
    )
    args = parser.parse_args()

    try:
        init_registry(force=args.force)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
