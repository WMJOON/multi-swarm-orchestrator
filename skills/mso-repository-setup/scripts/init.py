#!/usr/bin/env python3
"""
init.py — MSO Repository Setup CLI

사용법:
  init.py --target <path> [--name "Project Name"] [--id <project-id>]
  init.py --check <path>
  init.py --migrate <path>
  init.py --hook <path>

생성 구조:
  <target>/agent-context/
    ├── index/index.yaml          (root_offset: "../..")
    ├── workflow/
    └── work-memory/
        ├── schema.yaml
        ├── auditlog/  worklog/
        ├── track-record/{issue-note, agent-decision, user-decision, trouble-shooting}/
        └── insight-record/{episodes, patterns, principles}/

  <target>/.gitignore  (agent-context/work-memory/.zvec/ 등록)
  <target>/.claude/settings.json  (--hook 시 PostToolUse/Stop hook 등록)
"""

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"

AGENT_CONTEXT_TREE = [
    "index",
    "workflow",
    "work-memory/auditlog",
    "work-memory/worklog",
    "work-memory/track-record/issue-note",
    "work-memory/track-record/agent-decision",
    "work-memory/track-record/user-decision",
    "work-memory/track-record/trouble-shooting",
    "work-memory/insight-record/episodes",
    "work-memory/insight-record/patterns",
    "work-memory/insight-record/principles",
]

GITIGNORE_LINES = [
    "",
    "# MSO work-memory zvec index (regenerable)",
    "agent-context/work-memory/.zvec/",
]


def cmd_init(target: Path, name: str, project_id: str):
    if not target.exists():
        target.mkdir(parents=True)
        print(f"  + 프로젝트 디렉토리 생성: {target}")

    # 디렉토리 트리
    created = []
    for rel in AGENT_CONTEXT_TREE:
        p = target / "agent-context" / rel
        if not p.exists():
            p.mkdir(parents=True)
            created.append(rel)
    if created:
        print(f"  + agent-context/ 트리 생성 ({len(created)} 디렉토리)")
    else:
        print(f"  · agent-context/ 트리 (이미 존재)")

    # index.yaml
    index_path = target / "agent-context" / "index" / "index.yaml"
    if not index_path.exists():
        _write_index_template(index_path, name, project_id)
        print(f"  + agent-context/index/index.yaml 생성")
    else:
        print(f"  · agent-context/index/index.yaml (이미 존재)")

    # work-memory/schema.yaml
    schema_path = target / "agent-context" / "work-memory" / "schema.yaml"
    if not schema_path.exists():
        # mso-work-memory 스킬의 references/schema.yaml 을 복사 (있을 경우)
        wm_schema = _find_wm_schema()
        if wm_schema:
            shutil.copy(wm_schema, schema_path)
            print(f"  + work-memory/schema.yaml 복사 (mso-work-memory 표준)")
        else:
            _write_minimal_schema(schema_path)
            print(f"  + work-memory/schema.yaml 생성 (minimal — 표준 스킬 미발견)")
    else:
        print(f"  · work-memory/schema.yaml (이미 존재)")

    # .gitignore
    gi_path = target / ".gitignore"
    _ensure_gitignore(gi_path)

    print()
    print(f"✓ MSO repository setup 완료: {target}")
    print()
    print("다음 단계:")
    print("  1. scaffold 정의:  mso-scaffold-design  (index.yaml 모듈·subdir 등록)")
    print("  2. workflow 정의:  mso-workflow-design  (workflow YAML 작성)")
    print("  3. work-memory 사용: mso-work-memory   (entry 생성·검색·그래프)")


def _find_wm_schema() -> Path | None:
    """mso-work-memory 스킬의 references/schema.yaml 위치 탐색."""
    candidates = [
        Path.home() / ".claude" / "skills" / "mso-work-memory" / "references" / "schema.yaml",
        Path(__file__).parent.parent.parent / "mso-work-memory" / "references" / "schema.yaml",
    ]
    return next((p for p in candidates if p.exists()), None)


def _write_index_template(path: Path, name: str, project_id: str):
    today = dt.date.today().isoformat()
    content = f"""project:
  name: "{name}"
  id: "{project_id}"
  description: "TODO: 프로젝트 한 문장 요약"
  owner: "TODO@example.com"
  updated: "{today}"
  version: "0.1.0"
  root_offset: "../.."

modules: []

root_files: []
"""
    path.write_text(content, encoding="utf-8")


def _write_minimal_schema(path: Path):
    content = """# Work-Memory JSONL 공통 스키마 (minimal — mso-work-memory 설치 후 표준으로 교체 권장)
version: "0.1.0"
required_fields:
  id: "TYPE-NNNN"
  type: "issue-note | agent-decision | user-decision | trouble-shooting | episode | pattern | principle | auditlog | worklog"
  title: "한 줄 요약"
  text: "본문"
  tags: "list[str]"
  created_at: "ISO 8601"
"""
    path.write_text(content, encoding="utf-8")


def _ensure_gitignore(path: Path):
    existing = path.read_text() if path.exists() else ""
    if "agent-context/work-memory/.zvec" in existing:
        print(f"  · .gitignore (이미 등록됨)")
        return
    with open(path, "a", encoding="utf-8") as f:
        for line in GITIGNORE_LINES:
            f.write(line + "\n")
    print(f"  + .gitignore 갱신")


def cmd_check(target: Path):
    print(f"\nChecking MSO repository setup at: {target}\n")
    missing = []
    for rel in AGENT_CONTEXT_TREE:
        p = target / "agent-context" / rel
        if not p.exists():
            missing.append(rel)

    must_files = [
        ("agent-context/index/index.yaml", target / "agent-context" / "index" / "index.yaml"),
        ("agent-context/work-memory/schema.yaml", target / "agent-context" / "work-memory" / "schema.yaml"),
        (".gitignore", target / ".gitignore"),
    ]
    missing_files = [name for name, p in must_files if not p.exists()]

    if not missing and not missing_files:
        print("  ✓ 표준 구조에 부합합니다.")
        return 0
    if missing:
        print("[누락 디렉토리]")
        for m in missing:
            print(f"  ✗ agent-context/{m}")
    if missing_files:
        print("\n[누락 파일]")
        for m in missing_files:
            print(f"  ✗ {m}")
    print("\n→ `init.py --target {target}` 로 부트스트랩.")
    return 1


def cmd_migrate(target: Path):
    """기존 평탄 구조(index.yaml, workflow/ 가 루트에 있는) → agent-context/ 이전."""
    flat_index = target / "index.yaml"
    flat_workflow = target / "workflow"

    print(f"\nMigrating flat structure → agent-context/ at: {target}\n")

    # 구조 부트스트랩 (이미 있어도 무방)
    cmd_init(target, "TODO", "TODO")

    ac_index = target / "agent-context" / "index" / "index.yaml"
    ac_workflow = target / "agent-context" / "workflow"

    if flat_index.exists() and not (ac_index.exists() and ac_index.stat().st_size > 200):
        # 기존 index.yaml 을 agent-context/index/ 로 이동 (덮어쓰기)
        if ac_index.exists():
            ac_index.unlink()
        flat_index.rename(ac_index)
        print(f"  ↻ index.yaml → agent-context/index/index.yaml")
        print(f"  ! 이 파일에 'root_offset: \"../..\"' 를 project: 섹션에 수동 추가하세요.")

    if flat_workflow.exists() and flat_workflow.is_dir():
        for item in flat_workflow.iterdir():
            dest = ac_workflow / item.name
            if dest.exists():
                print(f"  · workflow/{item.name} (이미 존재, skip)")
                continue
            item.rename(dest)
            print(f"  ↻ workflow/{item.name} → agent-context/workflow/{item.name}")
        try:
            flat_workflow.rmdir()
            print(f"  - 빈 workflow/ 삭제")
        except OSError:
            print(f"  ! workflow/ 비어있지 않음 (수동 정리 필요)")

    print(f"\n✓ migrate 완료. `init.py --check {target}` 로 확인.")


HOOK_FILES = ["auditlog.py", "worklog.py", "work-memory-check.sh"]


def cmd_hook(target: Path, worthy_paths: str | None = None):
    """프로젝트의 .claude/ 에 work-memory hook 을 등록한다 (copy-form).

    hook 스크립트를 <target>/.claude/scripts/ 로 복사하고, settings.json 은
    "$CLAUDE_PROJECT_DIR" 상대로 참조한다. 절대 경로(스킬의 iCloud 심볼릭 경로,
    init 시점 workmem 절대경로)를 커밋 대상 파일에 박지 않으므로 다른 머신·CI·
    경로 이동에도 견딘다 (MKB·umbrella house convention 과 일관).

    WM_WORTHY_PATHS 는 --worthy-paths 로 주입한다(미지정 시 스크립트 기본값 =
    오케스트레이션 레이어). data/·build 처럼 고빈도 경로는 제외하는 게 좋다.
    """
    # hook 스크립트 원본 위치 탐색: mso-work-memory/hooks/ (sibling skill)
    hooks_dir = _find_hooks_dir()
    if hooks_dir is None:
        print("[ERROR] mso-work-memory/hooks/ 를 찾을 수 없습니다.")
        print("  탐색 경로:")
        for p in _hook_candidates():
            print(f"    {p}")
        return 1

    # 1) hook 스크립트를 프로젝트 .claude/scripts/ 로 복사 (self-contained)
    scripts_dst = target / ".claude" / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for fn in HOOK_FILES:
        src = hooks_dir / fn
        if src.exists():
            shutil.copy(src, scripts_dst / fn)
            (scripts_dst / fn).chmod(0o755)
            copied.append(fn)

    # 2) settings.json 구성 — 경로는 $CLAUDE_PROJECT_DIR 상대로만 참조
    settings_path = target / ".claude" / "settings.json"
    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ! settings.json 파싱 실패 — 백업 후 새로 작성합니다.")
            settings_path.rename(settings_path.with_suffix(".json.bak"))

    hooks_section = existing.setdefault("hooks", {})

    pd = '"$CLAUDE_PROJECT_DIR"'
    workmem_env = 'WORKMEM_DIR="$CLAUDE_PROJECT_DIR/agent-context/work-memory"'
    worthy_env = f'WM_WORTHY_PATHS="{worthy_paths}" ' if worthy_paths else ""

    auditlog_cmd = f"{workmem_env} python3 {pd}/.claude/scripts/auditlog.py"
    worklog_cmd = f"{workmem_env} python3 {pd}/.claude/scripts/worklog.py"
    check_cmd = f"{worthy_env}{workmem_env} bash {pd}/.claude/scripts/work-memory-check.sh"

    # PostToolUse — auditlog (도구 호출 감사 로그)
    _upsert_hook(hooks_section, "PostToolUse", "Bash|Edit|MultiEdit|Write", auditlog_cmd, "auditlog.py")
    # Stop / PreCompact — worklog 스냅샷 (파일 기록 — stdout 전달 의미론과 무관)
    for event, matcher in (("Stop", None), ("PreCompact", "auto")):
        _upsert_hook(hooks_section, event, matcher, worklog_cmd, "worklog.py")
    # work-memory-check 넛지 — 출력이 *모델 컨텍스트에 도달하는* 이벤트에만 등록한다.
    #   Stop          → 훅이 hookSpecificOutput.additionalContext JSON 으로 비차단 주입
    #   SessionStart  → plain stdout 이 컨텍스트로 주입됨 (compact/resume 직후 세션 회고)
    # PreCompact·SessionEnd 의 plain stdout 은 모델에 도달하지 않으므로 등록하지 않는다.
    _upsert_hook(hooks_section, "Stop", None, check_cmd, "work-memory-check.sh")
    for matcher in ("compact", "resume"):
        _upsert_hook(hooks_section, "SessionStart", matcher, check_cmd, "work-memory-check.sh")

    settings_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  + .claude/scripts/ 복사: {', '.join(copied)}")
    print(f"  + .claude/settings.json 갱신 (PostToolUse auditlog + Stop·PreCompact worklog + Stop·SessionStart[compact,resume] work-memory-check)")
    if worthy_paths:
        print(f"    WM_WORTHY_PATHS : {worthy_paths}")
    print()
    judgment = hooks_dir.parent / "assets" / "work-memory-judgment.md"
    print(f"✓ Hook 등록 완료: {settings_path}")
    print()
    print("권장: 기록 '판단 기준'을 상시 로드되도록 아래 템플릿 블록을")
    print(f"      프로젝트의 CLAUDE.md / AGENTS.md 에 붙여넣으세요 (always-on 강제):")
    print(f"      {judgment}")
    return 0


def _hook_candidates() -> list[Path]:
    """mso-work-memory/hooks/ 탐색 후보 목록."""
    skill_root = Path(__file__).parent.parent.parent  # repository-test/skills/
    return [
        skill_root / "mso-work-memory" / "hooks",
        Path.home() / ".claude" / "skills" / "mso-work-memory" / "hooks",
    ]


def _find_hooks_dir() -> Path | None:
    return next((p for p in _hook_candidates() if (p / "auditlog.py").exists()), None)


def _upsert_hook(hooks: dict, event: str, matcher: str | None, command: str, marker: str):
    """hooks dict 에 event/matcher/command 를 추가한다. 이미 marker 가 있으면 update."""
    event_list: list = hooks.setdefault(event, [])

    # matcher 가 일치하는 기존 항목 탐색
    target_group = None
    for group in event_list:
        if matcher is None or group.get("matcher") == matcher:
            target_group = group
            break

    if target_group is None:
        target_group = {"hooks": []}
        if matcher is not None:
            target_group["matcher"] = matcher
        event_list.append(target_group)

    inner: list = target_group.setdefault("hooks", [])

    # marker 로 기존 항목 업데이트 또는 신규 추가
    for h in inner:
        if marker in h.get("command", ""):
            h["command"] = command
            return
    inner.append({"type": "command", "command": command})


def main():
    parser = argparse.ArgumentParser(description="MSO Repository Setup", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", help="새 프로젝트 init")
    g.add_argument("--check", help="기존 구조 점검")
    g.add_argument("--migrate", help="평탄 구조 → agent-context/ 이전")
    g.add_argument("--hook", help=".claude/ 에 work-memory hook 복사·등록 (copy-form)")
    parser.add_argument("--name", default="TODO Project", help="프로젝트 표시 이름")
    parser.add_argument("--id", default="TODO-project-id", dest="project_id", help="프로젝트 id")
    parser.add_argument("--worthy-paths", dest="worthy_paths", default=None,
                        help="--hook 시 WM_WORTHY_PATHS 주입 (공백 구분 경로 목록). "
                             "예: \"scripts config .github/workflows .claude README.md\"")

    args = parser.parse_args()
    if args.target:
        cmd_init(Path(args.target).resolve(), args.name, args.project_id)
    elif args.check:
        sys.exit(cmd_check(Path(args.check).resolve()))
    elif args.migrate:
        cmd_migrate(Path(args.migrate).resolve())
    elif args.hook:
        sys.exit(cmd_hook(Path(args.hook).resolve(), args.worthy_paths))


if __name__ == "__main__":
    main()
