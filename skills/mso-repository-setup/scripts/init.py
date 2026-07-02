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
        ├── auditlog/  worklog/                       # 일별/시각별 append JSONL
        ├── track-record/                             # <type>.jsonl  예: user-decision.jsonl
        └── insight-record/                           # <type>.jsonl  예: episode.jsonl, pattern.jsonl

  <target>/.gitignore  (agent-context/work-memory/.zvec/, .claude/state/ 등록)
  <target>/.claude/settings.json  (--hook 시 Claude Code hook 등록)
  <target>/.codex/hooks.json      (--hook --provider codex 시 Codex hook 등록, compatibility)
  <target>/.codex/config.toml     (--hook --provider codex 시 Codex hook 등록)
"""

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"

# schema v1.2.0: track/insight 는 타입별 aggregate <type>.jsonl 로 저장된다.
# 타입별 하위디렉토리를 미리 만들지 않고 부모 디렉토리만 둔다 — 파일은 첫 append
# (wm_node.py new) 시점에 생성된다. 빈 부모 디렉토리는 .gitkeep 으로 추적한다.
AGENT_CONTEXT_TREE = [
    "index",
    "workflow",
    "work-memory/auditlog",
    "work-memory/worklog",
    "work-memory/track-record",
    "work-memory/insight-record",
]

GITIGNORE_LINES = [
    "",
    "# MSO work-memory zvec index (regenerable)",
    "agent-context/work-memory/.zvec/",
    "",
    "# MSO hook runtime state (local)",
    ".claude/state/",
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
        # work-memory 하위 빈 디렉토리는 .gitkeep 으로 git 추적 (첫 entry append 전까지).
        if rel.startswith("work-memory/") and not any(p.iterdir()):
            (p / ".gitkeep").touch()
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
    print("  2. workflow 정의:  mso-workflow-design  (workflow TTL ABox 작성 / legacy YAML 마이그레이션)")
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
  type: "issue-note | agent-decision | alternatives-record | user-decision | trouble-shooting | episode | pattern | principle | auditlog | worklog"
  title: "한 줄 요약"
  text: "본문"
  tags: "list[str]"
  created_at: "ISO 8601"
types:
  issue-note: {prefix: IN, dir: track-record}
  agent-decision: {prefix: AD, dir: track-record}
  alternatives-record: {prefix: AR, dir: track-record}
  user-decision: {prefix: UD, dir: track-record}
  trouble-shooting: {prefix: TS, dir: track-record}
  episode: {prefix: EP, dir: insight-record}
  pattern: {prefix: PT, dir: insight-record}
  principle: {prefix: PR, dir: insight-record}
  auditlog: {prefix: AU, dir: auditlog}
  worklog: {prefix: WL, dir: worklog}
relation_types:
  raised: "issue/case raises decision or alternatives"
  followed-by: "next lifecycle step"
  resolved-by: "issue resolved by troubleshooting"
  references: "reference edge"
  supersedes: "newer decision replaces older decision"
  refines: "newer decision refines older decision"
type_specific:
  alternatives-record:
    metadata:
      - provided_by: "agent | user"
      - options: "list[{n, name, description, trade_off}]"
      - recommended: "int"
  user-decision:
    metadata:
      - boundary: "policy/criterion boundary id for drift tracking"
      - criterion: "decision criterion in comparable one-line form"
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


WORK_MEMORY_HOOK_FILES = ["auditlog.py", "commit-work-memory.sh", "work-memory-check.sh", "stop-check.sh"]
SCAFFOLD_HOOK_FILES = ["scaffold-check.sh"]


def cmd_hook(target: Path, worthy_paths: str | None = None, provider: str = "claude"):
    """프로젝트의 provider 설정 디렉토리에 work-memory hook 을 등록한다 (copy-form).

    기본값은 기존 Claude Code 동작을 보존한다. `--provider codex` 를 지정하면
    <target>/.codex/scripts/ 를 만들고 <target>/.codex/config.toml 에 hook 을 등록한다.
    <target>/.codex/hooks.json 도 compatibility 파일로 함께 갱신한다. 절대 경로
    (스킬의 로컬 심볼릭 경로, init 시점 workmem 절대경로)를 커밋 대상 파일에
    박지 않으므로 다른 머신·CI·경로 이동에도 견딘다.

    WM_WORTHY_PATHS 는 --worthy-paths 로 주입한다(미지정 시 스크립트 기본값 =
    오케스트레이션 레이어). data/·build 처럼 고빈도 경로는 제외하는 게 좋다.
    """
    if provider not in {"claude", "codex"}:
        print(f"[ERROR] 지원하지 않는 provider: {provider}")
        return 1

    # hook 스크립트 원본 위치 탐색: mso-work-memory/hooks/ (sibling skill)
    hooks_dir = _find_hooks_dir()
    if hooks_dir is None:
        print("[ERROR] mso-work-memory/hooks/ 를 찾을 수 없습니다.")
        print("  탐색 경로:")
        for p in _hook_candidates():
            print(f"    {p}")
        return 1
    scaffold_skill_dir = _find_scaffold_skill_dir()
    if scaffold_skill_dir is None:
        print("[ERROR] mso-scaffold-design/ 를 찾을 수 없습니다.")
        print("  탐색 경로:")
        for p in _scaffold_skill_candidates():
            print(f"    {p}")
        return 1

    provider_dir_name = ".claude" if provider == "claude" else ".codex"
    settings_name = "settings.json" if provider == "claude" else "hooks.json"

    # 1) hook 스크립트를 프로젝트 provider scripts/ 로 복사 (self-contained)
    scripts_dst = target / provider_dir_name / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for fn in WORK_MEMORY_HOOK_FILES:
        src = hooks_dir / fn
        if src.exists():
            shutil.copy(src, scripts_dst / fn)
            (scripts_dst / fn).chmod(0o755)
            copied.append(fn)
    scaffold_hooks_dir = scaffold_skill_dir / "hooks"
    for fn in SCAFFOLD_HOOK_FILES:
        src = scaffold_hooks_dir / fn
        if src.exists():
            shutil.copy(src, scripts_dst / fn)
            (scripts_dst / fn).chmod(0o755)
            copied.append(fn)

    # scaffold-check.sh uses sf_node.py and its schema directory. Copy them into
    # the provider dir so project hooks do not depend on the original skill path.
    sf_src = scaffold_skill_dir / "scripts" / "sf_node.py"
    schema_src = scaffold_skill_dir / "references" / "schemas"
    if sf_src.exists():
        shutil.copy(sf_src, scripts_dst / "sf_node.py")
        (scripts_dst / "sf_node.py").chmod(0o755)
        copied.append("sf_node.py")
    if schema_src.exists():
        schema_dst = target / provider_dir_name / "references" / "schemas"
        if schema_dst.exists():
            shutil.rmtree(schema_dst)
        schema_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(schema_src, schema_dst)
        copied.append("scaffold schemas")

    # 2) hook 설정 구성 — 경로는 provider project dir 상대로만 참조
    settings_path = target / provider_dir_name / settings_name
    existing: dict = {}
    if provider == "codex":
        # Codex uses config.toml as the canonical hook surface. Keep hooks.json as
        # an inert compatibility file so older project-level hooks do not run twice.
        existing = {"hooks": {}}
    elif settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ! settings.json 파싱 실패 — 백업 후 새로 작성합니다.")
            settings_path.rename(settings_path.with_suffix(".json.bak"))

    hooks_section = existing.setdefault("hooks", {})

    if provider == "claude":
        pd = '"$CLAUDE_PROJECT_DIR"'
        workmem_env = 'WORKMEM_DIR="$CLAUDE_PROJECT_DIR/agent-context/work-memory"'
        prefix = ""
    else:
        pd = '"$PROJECT_DIR"'
        workmem_env = 'WORKMEM_DIR="$PROJECT_DIR/agent-context/work-memory"'
        prefix = 'export PROJECT_DIR="${CODEX_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"; '
    worthy_env = f'WM_WORTHY_PATHS="{worthy_paths}" ' if worthy_paths else ""

    auditlog_cmd = f"{prefix}{workmem_env} python3 {pd}/{provider_dir_name}/scripts/auditlog.py"
    commit_cmd = f"{prefix}{workmem_env} bash {pd}/{provider_dir_name}/scripts/commit-work-memory.sh"
    check_cmd = f"{prefix}{worthy_env}{workmem_env} bash {pd}/{provider_dir_name}/scripts/work-memory-check.sh"
    stop_check_cmd = f"{prefix}bash {pd}/{provider_dir_name}/scripts/stop-check.sh"
    scaffold_cmd = f"{prefix}MSO_SCAFFOLD_TOOL={pd}/{provider_dir_name}/scripts/sf_node.py bash {pd}/{provider_dir_name}/scripts/scaffold-check.sh"

    # Claude Code supports tool-level PostToolUse audit logging. Codex hook examples
    # available locally are lifecycle-only, so Codex keeps commit/check hooks only.
    if provider == "claude":
        _upsert_hook(hooks_section, "PostToolUse", "Bash|Edit|MultiEdit|Write", auditlog_cmd, "auditlog.py")
        _upsert_hook(hooks_section, "PostToolUse", "Bash|Edit|MultiEdit|Write", scaffold_cmd, "scaffold-check.sh")
        _upsert_hook(hooks_section, "Stop", None, stop_check_cmd, "stop-check.sh")

        # Stop / PreCompact — work-memory 변경분을 훅 안에서 커밋한다.
        # 훅 커밋은 PostToolUse 를 재트리거하지 않아 auditlog append 무한루프를 피한다.
        # worklog 는 workflow TTL node 실행 기록이므로 Stop hook 에서 자동 생성하지 않는다.
        for event, matcher in (("Stop", None), ("PreCompact", "auto")):
            _upsert_hook(hooks_section, event, matcher, commit_cmd, "commit-work-memory.sh")
        # work-memory-check 넛지 — provider 간 공통으로 확인된 SessionStart 에만 둔다.
        for matcher in ("compact", "resume"):
            _upsert_hook(hooks_section, "SessionStart", matcher, check_cmd, "work-memory-check.sh")
            _upsert_hook(hooks_section, "SessionStart", matcher, scaffold_cmd, "scaffold-check.sh")

    settings_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if provider == "codex":
        _upsert_codex_config_toml(
            target / provider_dir_name / "config.toml",
            commit_cmd=commit_cmd,
            check_cmd=check_cmd,
            scaffold_cmd=scaffold_cmd,
        )
    print(f"  + {provider_dir_name}/scripts/ 복사: {', '.join(copied)}")
    if provider == "claude":
        print(f"  + .claude/settings.json 갱신 (PostToolUse auditlog/scaffold-check + Stop stop-check/commit-work-memory + PreCompact commit-work-memory + SessionStart[compact,resume] work-memory-check/scaffold-check)")
    else:
        print(f"  + .codex/config.toml 갱신 (Stop·PreCompact commit-work-memory + SessionStart[compact,resume] work-memory-check/scaffold-check)")
        print(f"  + .codex/hooks.json 갱신 (empty compatibility)")
    if worthy_paths:
        print(f"    WM_WORTHY_PATHS : {worthy_paths}")
    print()
    judgment = hooks_dir.parent / "assets" / "work-memory-judgment.md"
    print(f"✓ Hook 등록 완료: {settings_path}")
    print()
    print("권장: 기록 '판단 기준'을 상시 로드되도록 아래 템플릿 블록을")
    print(f"      프로젝트의 AGENTS.md / CLAUDE.md 에 붙여넣으세요 (always-on 강제):")
    print(f"      {judgment}")
    return 0


def _hook_candidates() -> list[Path]:
    """mso-work-memory/hooks/ 탐색 후보 목록."""
    skill_root = Path(__file__).parent.parent.parent  # repository/skills/
    return [
        skill_root / "mso-work-memory" / "hooks",
        Path.home() / ".claude" / "skills" / "mso-work-memory" / "hooks",
        Path.home() / ".codex" / "skills" / "mso-work-memory" / "hooks",
    ]


def _find_hooks_dir() -> Path | None:
    return next((p for p in _hook_candidates() if (p / "auditlog.py").exists()), None)


def _scaffold_skill_candidates() -> list[Path]:
    """mso-scaffold-design/ 탐색 후보 목록."""
    skill_root = Path(__file__).parent.parent.parent  # repository/skills/
    return [
        skill_root / "mso-scaffold-design",
        Path.home() / ".claude" / "skills" / "mso-scaffold-design",
        Path.home() / ".codex" / "skills" / "mso-scaffold-design",
    ]


def _find_scaffold_skill_dir() -> Path | None:
    return next((p for p in _scaffold_skill_candidates() if (p / "scripts" / "sf_node.py").exists()), None)


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


def _toml_literal(value: str) -> str:
    """Return a TOML literal string. Commands generated here do not contain single quotes."""
    if "'" in value:
        return json.dumps(value, ensure_ascii=False)
    return f"'{value}'"


def _ensure_codex_hooks_feature(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "[features]":
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                if lines[j].strip().startswith("hooks"):
                    return text
                j += 1
            lines.insert(i + 1, "hooks = true")
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    prefix = "[features]\nhooks = true\n\n"
    return prefix + text


def _upsert_codex_config_toml(config_path: Path, commit_cmd: str, check_cmd: str, scaffold_cmd: str):
    """Add a managed MSO hook block to .codex/config.toml."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    text = _remove_managed_block(text, "MSO_WORK_MEMORY_HOOKS")
    text = _ensure_codex_hooks_feature(text)
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"

    block = f"""# BEGIN MSO_WORK_MEMORY_HOOKS
# Managed by mso-repository-setup scripts/init.py --hook --provider codex.
[[hooks.Stop]]

[[hooks.Stop.hooks]]
type = "command"
command = {_toml_literal(commit_cmd)}
statusMessage = "Committing MSO work-memory"

[[hooks.PreCompact]]
matcher = "auto"

[[hooks.PreCompact.hooks]]
type = "command"
command = {_toml_literal(commit_cmd)}
statusMessage = "Committing MSO work-memory before compaction"

[[hooks.SessionStart]]
matcher = "compact"

[[hooks.SessionStart.hooks]]
type = "command"
command = {_toml_literal(check_cmd)}
statusMessage = "Checking MSO work-memory reminders"

[[hooks.SessionStart.hooks]]
type = "command"
command = {_toml_literal(scaffold_cmd)}
statusMessage = "Checking MSO scaffold inventory"

[[hooks.SessionStart]]
matcher = "resume"

[[hooks.SessionStart.hooks]]
type = "command"
command = {_toml_literal(check_cmd)}
statusMessage = "Checking MSO work-memory reminders"

[[hooks.SessionStart.hooks]]
type = "command"
command = {_toml_literal(scaffold_cmd)}
statusMessage = "Checking MSO scaffold inventory"
# END MSO_WORK_MEMORY_HOOKS
"""
    config_path.write_text(text + block, encoding="utf-8")


def _remove_managed_block(text: str, name: str) -> str:
    start = f"# BEGIN {name}"
    end = f"# END {name}"
    if start not in text:
        return text
    before, rest = text.split(start, 1)
    if end not in rest:
        return before.rstrip() + "\n"
    _, after = rest.split(end, 1)
    return (before.rstrip() + "\n\n" + after.lstrip()).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="MSO Repository Setup", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", help="새 프로젝트 init")
    g.add_argument("--check", help="기존 구조 점검")
    g.add_argument("--migrate", help="평탄 구조 → agent-context/ 이전")
    g.add_argument("--hook", help="provider 설정 디렉토리에 work-memory hook 복사·등록 (copy-form)")
    parser.add_argument("--name", default="TODO Project", help="프로젝트 표시 이름")
    parser.add_argument("--id", default="TODO-project-id", dest="project_id", help="프로젝트 id")
    parser.add_argument("--provider", choices=("claude", "codex"), default="claude",
                        help="--hook 대상 provider. 기본값 claude 는 기존 동작을 보존한다.")
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
        sys.exit(cmd_hook(Path(args.hook).resolve(), args.worthy_paths, args.provider))


if __name__ == "__main__":
    main()
