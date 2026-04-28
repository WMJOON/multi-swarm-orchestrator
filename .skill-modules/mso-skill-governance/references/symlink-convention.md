# Symlink Convention — Tool Lifecycle 경로 규약

> Smart Tool의 Lifecycle 상태별 경로 패턴과 symlink 생성/관리 규칙.
> `module.tool-lifecycle.md`의 참조 문서.

---

## 경로 패턴

### Local 상태

```
{workspace}/tools/{tool_name}/
├── manifest.json         ← lifecycle_state: "local"
├── slots/
│   ├── input_norm/
│   ├── rules/
│   ├── inference/
│   │   ├── model/
│   │   └── serve.py
│   └── script/
├── schemas/
│   ├── input.schema.json
│   └── output.schema.json
└── README.md
```

- `{workspace}`: MSO_WORKSPACE_ROOT 환경변수 또는 프로젝트 루트
- Tool 생성 시 기본 상태
- 해당 workspace만 접근 가능

### Symlinked 상태

```
~/.claude/global_links/{tool_name}/    ← symlink → {owner_workspace}/tools/{tool_name}/
├── manifest.json                       ← lifecycle_state: "symlinked"
├── slots/
│   └── (원본과 동일 — symlink 경유)
├── schemas/
└── README.md
```

- `~/.claude/global_links/`는 모든 workspace에서 접근 가능한 공유 디렉토리
- symlink target은 반드시 `owner_workspace`의 원본 Tool 디렉토리
- 다른 workspace는 이 symlink를 통해 read-only로 참조

### Global 상태

```
~/.claude/skills/{tool_name}/
├── SKILL.md               ← 공식 스킬 문서 (Claude Code 트리거 적용)
├── manifest.json           ← lifecycle_state: "global"
├── slots/
│   └── (추상화 완료된 코드)
├── schemas/
├── modules/                ← 모듈 문서 (필요시)
└── README.md
```

- `~/.claude/skills/`에 등록된 스킬은 전역 트리거로 활성화
- manifest.json의 `owner_workspace: null`
- SKILL.md가 Claude Code의 스킬 인식 진입점

---

## Symlink 생성 절차

### Local → Symlinked

```bash
# 1. 원본 확인
ls {workspace}/tools/{tool_name}/manifest.json

# 2. global_links 디렉토리 확인/생성
mkdir -p ~/.claude/global_links/

# 3. symlink 생성
ln -s {workspace}/tools/{tool_name} ~/.claude/global_links/{tool_name}

# 4. manifest.json 갱신
# lifecycle_state: "local" → "symlinked"
```

### Symlinked → Global

```bash
# 1. 추상화 검증 완료 확인 (abstraction_score ≤ 0.2)

# 2. skills 디렉토리에 복사 (symlink가 아닌 실제 복사)
cp -r ~/.claude/global_links/{tool_name} ~/.claude/skills/{tool_name}

# 3. SKILL.md 작성 (Claude Code 트리거 정의)

# 4. manifest.json 갱신
# lifecycle_state: "symlinked" → "global"
# owner_workspace: null

# 5. 기존 symlink 제거 (선택: global 등록 후에도 유지 가능)
```

---

## 쓰기 권한 규칙

| 상태 | 쓰기 권한 | 규칙 |
|------|-----------|------|
| Local | owner_workspace만 | 다른 workspace에서 접근 불가 |
| Symlinked | owner_workspace만 | 다른 workspace는 read-only. `manifest.json`의 `owner_workspace` 필드로 소유권 확인. |
| Global | HITL 승인 후 | 전역 영향이므로 사람 승인 필수. 승인 없는 수정은 governance 위반. |

### 충돌 방지 규칙

1. **동일 이름 금지**: `global_links/`에 같은 `tool_name`의 symlink가 이미 존재하면 생성 거부.
2. **owner 확인**: symlink 수정 시 `manifest.json`의 `owner_workspace`와 현재 workspace를 비교. 불일치 시 거부.
3. **dangling symlink 감지**: `mso-observability`가 주기적으로 `global_links/` 내 symlink 유효성을 확인. broken link 발견 시 `anomaly_detected` 이벤트 발생.

---

## tool_registry.json 연동

symlink 생성/제거 시 `{workspace}/.mso-context/tool_registry.json`의 해당 엔트리를 동기화한다.

| 행동 | registry 갱신 |
|------|--------------|
| symlink 생성 | `lifecycle_state: "symlinked"`, `manifest_path` 갱신 |
| global 등록 | `lifecycle_state: "global"`, `owner_workspace: null` |
| symlink 제거 (강등) | `lifecycle_state: "local"`, `manifest_path` 원본으로 복원 |

---

## 주의사항

- **절대 경로 금지**: Tool 내부 코드에서 절대 경로를 사용하면 symlink 경유 시 경로가 깨진다. 반드시 상대 경로 또는 환경변수 사용.
- **symlink 순환 금지**: `global_links/{tool_name}/` 내부에서 다시 `global_links/`를 참조하는 symlink 금지.
- **Git 호환성**: symlink는 Git에서 특별 취급된다. `.gitignore`에 `global_links/`를 추가하거나, Git의 `core.symlinks` 설정을 확인할 것.
