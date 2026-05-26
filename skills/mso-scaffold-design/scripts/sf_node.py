#!/usr/bin/env python3
"""
sf_node.py — Scaffold node schema tool

사용법:
  python sf_node.py show <type>                          # 스키마 출력
  python sf_node.py scaffold module --id <NN.name>       # 모듈 스캐폴드
  python sf_node.py scaffold subdir --path <NN.name/>    # 서브디렉토리 스캐폴드
  python sf_node.py validate <index.yaml>                # 스키마 검증 (계층 참조 자동 해석)
  python sf_node.py inventory <index.yaml> [--root .]    # 실제 FS와 대조 (계층 재귀)
  python sf_node.py tree <index.yaml>                    # 계층 구조 트리 출력 (디버깅)

type: project | module | subdir

계층 참조: module.sub_index 가 있으면 root index → sub index 로 재귀 해석.
- max_depth = 3 (root + 2단계). 초과 시 ERROR.
- 순환 참조 차단 (visited-set).
- 전역 module id unique.
"""

import argparse
import sys
import unicodedata
from pathlib import Path

import yaml

SCHEMAS_DIR = Path(__file__).parent.parent / "references" / "schemas"
MAX_DEPTH = 3


# ─── Schema loading ────────────────────────────────────────────────────────────

def load_schema(node_type: str) -> dict:
    path = SCHEMAS_DIR / f"{node_type}.schema.yaml"
    if not path.exists():
        sys.exit(f"[ERROR] 스키마 파일 없음: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


# ─── show ──────────────────────────────────────────────────────────────────────

def cmd_show(node_type: str):
    schema = load_schema(node_type)
    print(f"# {node_type} 노드 스키마\n")
    print(f"설명: {schema.get('description', '-')}\n")

    fields = schema.get("fields", {})
    print("## 필드")
    print(f"{'필드':<18} {'필수':<8} {'타입':<14} 설명")
    print("-" * 80)
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        required = "필수" if spec.get("required") else "선택"
        ftype = spec.get("type", "-")
        if ftype == "enum":
            ftype = f"enum"
        desc = (spec.get("description", "") or "").split("\n")[0]
        print(f"  {name:<16} {required:<8} {ftype:<14} {desc}")

    if "prefix_conventions" in schema:
        print("\n## Prefix 컨벤션")
        for p, role in schema["prefix_conventions"].items():
            print(f"  {p:<6}  {role}")

    if "path_prefix_role_mapping" in schema:
        print("\n## Path → Role 매핑")
        for p, role in schema["path_prefix_role_mapping"].items():
            print(f"  {p:<28} {role}")


# ─── scaffold ──────────────────────────────────────────────────────────────────

def cmd_scaffold(node_type: str, **kwargs):
    if node_type == "project":
        node = _scaffold_project()
        print(yaml.dump({"project": node}, allow_unicode=True, sort_keys=False).rstrip())
        return

    if node_type == "module":
        mid = kwargs.get("id")
        if not mid:
            sys.exit("[ERROR] --id 필수")
        node = _scaffold_module(mid)
    elif node_type == "subdir":
        path = kwargs.get("path")
        if not path:
            sys.exit("[ERROR] --path 필수")
        node = _scaffold_subdir(path)
    else:
        sys.exit(f"[ERROR] 지원하지 않는 type: {node_type}")

    print(yaml.dump([node], allow_unicode=True, sort_keys=False).rstrip())


def _scaffold_project() -> dict:
    return {
        "name": "TODO Project Name",
        "id": "NN.project-id",
        "description": "TODO: 프로젝트 한 문장 요약",
        "owner": "TODO@example.com",
        "updated": "YYYY-MM-DD",
        "version": "1.0.0",
    }


def _scaffold_module(mid: str) -> dict:
    if not mid.endswith("/"):
        path = f"{mid}/"
    else:
        path = mid
        mid = mid[:-1]
    return {
        "id": mid,
        "path": path,
        "description": "TODO: 모듈 한 문장 설명",
        "subdirs": [
            {"path": "00.context/", "role": "context", "description": "TODO"},
            {"path": "01.scripts/", "role": "scripts", "description": "TODO"},
        ],
        "key_files": ["README.md"],
        "status": "active",
    }


def _scaffold_subdir(path: str) -> dict:
    if not path.endswith("/"):
        path = path + "/"
    role = _infer_role(path)
    return {
        "path": path,
        "description": "TODO",
        "role": role,
    }


def _infer_role(path: str) -> str:
    schema = load_schema("subdir")
    mapping = schema.get("path_prefix_role_mapping", {})
    for prefix, role in mapping.items():
        if path.startswith(prefix.rstrip("-")) or (prefix.endswith("-") and path.startswith(prefix)):
            return role
    return "TODO"


# ─── Issue ─────────────────────────────────────────────────────────────────────

class Issue:
    def __init__(self, ctx: str, field: str, msg: str, level: str = "error"):
        self.ctx, self.field, self.msg, self.level = ctx, field, msg, level

    def __str__(self):
        tag = "ERROR" if self.level == "error" else "WARN "
        return f"  [{tag}] {self.ctx} / {self.field}: {self.msg}"


# ─── Resolver (계층 참조 해석) ─────────────────────────────────────────────────

class ResolvedScaffold:
    """sub_index 트리를 평탄화한 결과."""

    def __init__(self):
        self.project: dict | None = None              # root project 메타
        self.modules: list[dict] = []                 # 전역 평탄 모듈 목록
        self.module_sources: dict[str, Path] = {}     # module id → source yaml path
        self.module_fs_root: dict[str, Path] = {}     # module id → fs root (모듈 디렉토리 절대경로)
        self.fs_root: Path | None = None              # 프로젝트 루트 (root_offset 적용 후)
        self.issues: list[Issue] = []                 # 해석 중 발생한 issue

    def module_ids(self) -> set[str]:
        return {m.get("id") for m in self.modules if m.get("id")}


def _load_yaml(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        raise RuntimeError(f"YAML 파싱 실패: {path}: {e}")


def resolve_tree(root_yaml: str | Path, max_depth: int = MAX_DEPTH) -> ResolvedScaffold:
    """root index.yaml에서 시작해 sub_index 트리를 평탄화한다.

    - 전역 module id unique 검사
    - sub 파일의 project.id 가 root project.id 와 일치 확인
    - sub_index + local subdirs/key_files/references 충돌 검사
    - max_depth 초과 / 순환 / 경로 누락 ERROR
    - project.root_offset (옵션) — yaml 위치와 다른 프로젝트 루트 지정. 예: "../.." 이면
      yaml 부모의 부모의 부모가 프로젝트 루트. module.path 가 그 루트 기준 상대로 해석됨.
    """
    root_path = Path(root_yaml).resolve()
    resolved = ResolvedScaffold()

    root_doc = _load_yaml(root_path)
    if root_doc is None:
        resolved.issues.append(Issue("(root)", "file", f"파일 없음 또는 빈 yaml: {root_path}"))
        return resolved

    resolved.project = root_doc.get("project")
    root_project_id = (resolved.project or {}).get("id")

    # project.root_offset 처리 — yaml 위치 기준 상대로 프로젝트 루트 계산
    root_offset = (resolved.project or {}).get("root_offset")
    if root_offset:
        fs_root = (root_path.parent / root_offset).resolve()
    else:
        fs_root = root_path.parent.resolve()
    resolved.fs_root = fs_root

    visited: set[Path] = {root_path}
    _recurse_index(
        doc=root_doc,
        source=root_path,
        fs_root=fs_root,
        depth=1,
        max_depth=max_depth,
        visited=visited,
        resolved=resolved,
        root_project_id=root_project_id,
    )

    # 전역 module id unique
    seen: dict[str, Path] = {}
    for m in resolved.modules:
        mid = m.get("id")
        if not mid:
            continue
        src = resolved.module_sources.get(mid)
        if mid in seen:
            resolved.issues.append(Issue(
                f"module:{mid}", "id",
                f"전역 중복 id (다른 소스: {seen[mid]}, 현재 소스: {src})"
            ))
        else:
            seen[mid] = src

    return resolved


def _recurse_index(
    doc: dict,
    source: Path,
    fs_root: Path,
    depth: int,
    max_depth: int,
    visited: set[Path],
    resolved: ResolvedScaffold,
    root_project_id: str | None,
):
    """단일 index 문서를 처리하고, 각 module 의 sub_index 를 따라 재귀."""

    # root 외 파일에서 project.id 일치 검사
    if depth > 1:
        sub_proj = (doc.get("project") or {}).get("id")
        if sub_proj and root_project_id and sub_proj != root_project_id:
            resolved.issues.append(Issue(
                f"sub-index:{source.name}", "project.id",
                f"root project.id 와 불일치: sub={sub_proj}, root={root_project_id}"
            ))

    for m in doc.get("modules", []) or []:
        mid = m.get("id")
        mpath = m.get("path", "")
        sub_index_rel = m.get("sub_index")

        # depth > 1 에서 이미 등록된 module id 와 동일하면 "self-merge"
        # (sub 파일이 자기 모듈의 subdirs/key_files/references 를 채우는 패턴)
        existing = None
        if depth > 1 and mid:
            existing = next((x for x in resolved.modules if x.get("id") == mid), None)

        if existing is not None:
            # sub 가 SSOT — subdirs/key_files/references 를 sub 값으로 덮어쓰기
            for k in ("subdirs", "key_files", "references", "description", "status"):
                if k in m:
                    existing[k] = m[k]
            # source 는 sub 가 가장 자세한 정보를 가지므로 sub 로 갱신
            resolved.module_sources[mid] = source
            continue

        # 모듈 절대 fs_root 계산
        mod_fs = (fs_root / mpath).resolve() if mpath else fs_root
        if mid:
            resolved.module_fs_root[mid] = mod_fs
            resolved.module_sources[mid] = source

        if not sub_index_rel:
            # 평범한 모듈 (leaf)
            resolved.modules.append(m)
            continue

        # sub_index 존재 시 root 에서는 local subdirs/key_files/references 비어야 함
        if m.get("subdirs") or m.get("key_files") or m.get("references"):
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                "sub_index 가 있는 모듈의 subdirs/key_files/references 는 sub 파일에 둘 것 (root 비움)"
            ))

        # 모듈 entry 를 평탄 목록에 추가 (sub_index 키는 제외)
        resolved.modules.append({k: v for k, v in m.items() if k != "sub_index"})

        # depth 초과 검사
        if depth + 1 > max_depth:
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                f"max_depth({max_depth}) 초과: 현재 depth={depth+1}"
            ))
            continue

        # sub_index 파일 경로 해석 (root index 기준 상대 → 현재 fs_root 기준)
        sub_path = (fs_root / sub_index_rel).resolve()

        # sub_index 파일이 module.path 디렉토리의 자손이어야 함
        try:
            sub_path.relative_to(mod_fs)
        except ValueError:
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                f"sub_index 경로가 module.path 디렉토리 밖에 있음: {sub_path}"
            ))
            continue

        # 순환 차단
        if sub_path in visited:
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                f"순환 참조 감지: {sub_path}"
            ))
            continue

        if not sub_path.exists():
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                f"sub_index 파일 없음: {sub_path}"
            ))
            continue

        visited.add(sub_path)
        sub_doc = _load_yaml(sub_path)
        if sub_doc is None:
            resolved.issues.append(Issue(
                f"module:{mid}", "sub_index",
                f"sub_index 로드 실패: {sub_path}"
            ))
            continue

        _recurse_index(
            doc=sub_doc,
            source=sub_path,
            fs_root=mod_fs,
            depth=depth + 1,
            max_depth=max_depth,
            visited=visited,
            resolved=resolved,
            root_project_id=root_project_id,
        )


# ─── validate ─────────────────────────────────────────────────────────────────

def cmd_validate(yaml_path: str):
    path = Path(yaml_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 없음: {yaml_path}")

    resolved = resolve_tree(path)
    issues: list[Issue] = list(resolved.issues)

    issues.extend(_validate_project(resolved.project))
    issues.extend(_validate_modules_global(resolved))

    _print_issues(issues, yaml_path)
    return len([i for i in issues if i.level == "error"]) == 0


def _validate_project(project: dict | None) -> list[Issue]:
    if project is None:
        return [Issue("(document)", "project", "top-level `project:` 없음")]
    schema = load_schema("project")
    return _check_fields("project", project, schema["fields"])


def _validate_modules_global(resolved: ResolvedScaffold) -> list[Issue]:
    """전역(계층 평탄화) 모듈 목록 검증."""
    if not resolved.modules:
        return [Issue("(document)", "modules", "modules[] 없음 또는 비어있음")]
    issues: list[Issue] = []
    schema = load_schema("module")
    subdir_schema = load_schema("subdir")
    ids = resolved.module_ids()

    for m in resolved.modules:
        mid = m.get("id", "(no-id)")
        src = resolved.module_sources.get(mid)
        ctx_suffix = f" @ {src.name}" if src else ""
        ctx = f"module:{mid}{ctx_suffix}"
        issues.extend(_check_fields(ctx, m, schema["fields"]))

        # path '/' 종료
        if m.get("path") and not m["path"].endswith("/"):
            issues.append(Issue(ctx, "path", "끝에 '/' 필수"))

        # subdirs 검증
        seen_paths: set[str] = set()
        for sd in m.get("subdirs", []) or []:
            sd_ctx = f"{ctx}/subdir:{sd.get('path', '?')}"
            issues.extend(_check_fields(sd_ctx, sd, subdir_schema["fields"]))

            sp = sd.get("path")
            if sp:
                if not sp.endswith("/"):
                    issues.append(Issue(sd_ctx, "path", "끝에 '/' 필수"))
                if sp in seen_paths:
                    issues.append(Issue(sd_ctx, "path", "동일 모듈 내 중복 path"))
                seen_paths.add(sp)

        # references 전역 module id 풀로 검사
        for ref in m.get("references", []) or []:
            if "consumes" in ref and ref["consumes"] not in ids:
                issues.append(Issue(
                    ctx, "references.consumes",
                    f"존재하지 않는 모듈 id: {ref['consumes']}"
                ))
            for tgt in ref.get("provides_to", []) or []:
                if tgt not in ids:
                    issues.append(Issue(
                        ctx, "references.provides_to",
                        f"존재하지 않는 모듈 id: {tgt}", "warning"
                    ))

    return issues


def _check_fields(ctx: str, obj: dict, fields_spec: dict) -> list[Issue]:
    """구조적 검증만 수행. 네이밍 패턴은 프로젝트 컨벤션 영역."""
    issues: list[Issue] = []
    for fname, fspec in fields_spec.items():
        if not isinstance(fspec, dict):
            continue
        val = obj.get(fname)
        if fspec.get("required") and val in (None, "", []):
            issues.append(Issue(ctx, fname, "필수 필드 없음"))
            continue
        if val is None:
            continue

        if fspec.get("type") == "enum":
            allowed = fspec.get("values", [])
            if val not in allowed:
                issues.append(Issue(ctx, fname, f"허용값 아님: {val} (허용: {allowed})"))

    return issues


def _print_issues(issues: list[Issue], path: str):
    err = len([i for i in issues if i.level == "error"])
    warn = len([i for i in issues if i.level == "warning"])

    print(f"\n검증: {path}")
    print(f"결과: ERROR {err}개, WARNING {warn}개\n")

    if not issues:
        print("  ✓ 스키마 준수.")
        return
    for i in issues:
        icon = "✗" if i.level == "error" else "△"
        print(f"  {icon} {i}")
    if err > 0:
        print(f"\n→ {err}개 오류 수정 후 재실행.")


# ─── inventory ─────────────────────────────────────────────────────────────────

def cmd_inventory(yaml_path: str, root: str | None = None):
    path = Path(yaml_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 없음: {yaml_path}")

    resolved = resolve_tree(path)
    # --root 명시 우선 > project.root_offset > yaml 부모
    if root:
        fs_root = Path(root).resolve()
    elif resolved.fs_root is not None:
        fs_root = resolved.fs_root
    else:
        fs_root = path.parent.resolve()

    print(f"\nInventory check: index={yaml_path}, root={fs_root}")
    print(f"(계층 모듈 {len(resolved.modules)}개 인식)\n")

    if resolved.issues:
        print("[해석 단계 issue]")
        for i in resolved.issues:
            print(str(i))
        print()

    missing: list[str] = []   # 선언됐는데 FS에 없음
    extra: list[str] = []     # FS에 있는데 선언 안 됨

    def _nfc(p: Path) -> str:
        return unicodedata.normalize("NFC", str(p.resolve()))

    # 선언된 모든 디렉토리 (모듈 + subdirs)
    declared: set[str] = set()
    declared_module_roots_per_parent: dict[str, set[str]] = {}
    # 모듈별로 어느 fs_root 안의 모듈인지 추적
    for m in resolved.modules:
        mid = m.get("id")
        mod_fs = resolved.module_fs_root.get(mid)
        if not mod_fs:
            continue
        declared.add(_nfc(mod_fs))
        # parent 별로 모듈 루트 집계 (extra 검출용)
        parent = str(mod_fs.parent.resolve())
        declared_module_roots_per_parent.setdefault(parent, set()).add(_nfc(mod_fs))

        if not mod_fs.exists():
            try:
                rel = mod_fs.relative_to(fs_root)
                missing.append(f"module: {rel}/")
            except ValueError:
                missing.append(f"module: {mod_fs}")
            continue

        for sd in m.get("subdirs", []) or []:
            sp = sd.get("path", "")
            sub_full = (mod_fs / sp).resolve()
            declared.add(_nfc(sub_full))
            if not sub_full.exists():
                try:
                    rel = sub_full.relative_to(fs_root)
                    missing.append(f"subdir: {rel}")
                except ValueError:
                    missing.append(f"subdir: {sub_full}")

    # extra: 각 모듈 루트의 parent 디렉토리에서, 선언되지 않은 top-level 디렉토리
    # 단, fs_root 자체에 대해서는 root index 가 모듈 루트의 parent
    parents_to_scan = set(declared_module_roots_per_parent.keys())
    parents_to_scan.add(str(fs_root))

    for parent_str in parents_to_scan:
        parent = Path(parent_str)
        if not parent.is_dir():
            continue
        try:
            children = [d for d in parent.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name != "agent-context"]
        except PermissionError:
            continue
        declared_here = declared_module_roots_per_parent.get(parent_str, set())
        for d in children:
            if _nfc(d) in declared_here:
                continue
            if _nfc(d) in declared:
                continue
            # parent 가 어떤 모듈의 자식인 경우, 그 모듈의 subdirs 에 등록됐는지도 확인
            # → declared 에 이미 포함되어 있다면 skip (위에서 검사됨)
            try:
                rel = d.relative_to(fs_root)
            except ValueError:
                rel = d.name
            extra.append(f"unregistered dir: {rel}")

    if not missing and not extra:
        print("  ✓ 선언과 실제 트리가 일치합니다.")
        return

    if missing:
        print("[MISSING] 선언됐으나 파일시스템에 없음:")
        for m in missing:
            print(f"  ✗ {m}")
    if extra:
        print("\n[EXTRA] 파일시스템에 있으나 선언 안됨:")
        for e in extra:
            print(f"  △ {e}")


# ─── tree (계층 구조 출력) ────────────────────────────────────────────────────

def cmd_tree(yaml_path: str):
    path = Path(yaml_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 없음: {yaml_path}")

    resolved = resolve_tree(path)
    print(f"\nScaffold tree: {yaml_path}")
    project = resolved.project or {}
    print(f"project: {project.get('id', '?')} — {project.get('name', '?')}\n")

    if not resolved.modules:
        print("  (모듈 없음)")
        return

    # source file 기준으로 그룹핑
    by_source: dict[Path, list[dict]] = {}
    for m in resolved.modules:
        src = resolved.module_sources.get(m.get("id")) or path
        by_source.setdefault(src, []).append(m)

    print(f"총 모듈 수 (계층 평탄화): {len(resolved.modules)}\n")
    for src, mods in by_source.items():
        try:
            rel = src.relative_to(path.parent.resolve())
        except ValueError:
            rel = src
        print(f"[source: {rel}]")
        for m in mods:
            mid = m.get("id", "?")
            mpath = m.get("path", "?")
            sub = " [sub_index ↓]" if m.get("sub_index") else ""
            print(f"  - {mid:<30} {mpath}{sub}")
            for sd in m.get("subdirs", []) or []:
                print(f"      └ {sd.get('path', '?'):<24} {sd.get('description', '')[:50]}")
        print()

    if resolved.issues:
        print("[해석 단계 issue]")
        for i in resolved.issues:
            print(str(i))


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scaffold node schema tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="노드 유형 스키마 출력")
    p_show.add_argument("type", choices=["project", "module", "subdir"])

    p_sc = sub.add_parser("scaffold", help="노드 스캐폴드 YAML 생성")
    p_sc.add_argument("type", choices=["project", "module", "subdir"])
    p_sc.add_argument("--id", help="module id (예: 05.new-module)")
    p_sc.add_argument("--path", help="subdir path (예: 02.data/)")

    p_val = sub.add_parser("validate", help="index.yaml 검증 (계층 자동 해석)")
    p_val.add_argument("yaml", help="검증할 index.yaml 경로")

    p_inv = sub.add_parser("inventory", help="선언과 실제 디렉토리 트리 대조 (계층 재귀)")
    p_inv.add_argument("yaml", help="index.yaml 경로")
    p_inv.add_argument("--root", help="프로젝트 루트 (생략 시 yaml 부모)")

    p_tree = sub.add_parser("tree", help="계층 scaffold 트리 출력 (디버깅)")
    p_tree.add_argument("yaml", help="root index.yaml 경로")

    args = parser.parse_args()

    if args.cmd == "show":
        cmd_show(args.type)
    elif args.cmd == "scaffold":
        cmd_scaffold(args.type, id=args.id, path=args.path)
    elif args.cmd == "validate":
        ok = cmd_validate(args.yaml)
        sys.exit(0 if ok else 1)
    elif args.cmd == "inventory":
        cmd_inventory(args.yaml, args.root)
    elif args.cmd == "tree":
        cmd_tree(args.yaml)


if __name__ == "__main__":
    main()
