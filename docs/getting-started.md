# 시작하기 (v0.3.0)

## 0. 설치

```bash
# 옵션 A: install.sh (직접 symlink)
bash install.sh               # Claude Code 전용
bash install.sh --all         # Claude + Codex + Gemini

# 옵션 B: sync-agents-global.sh (글로벌 링크 허브 경유)
bash 00_agents_global_links/sync-agents-global.sh sync
```

설치 후 `~/.claude/skills/` 에 5개 스킬이 등록된다.

---

## 1. 새 프로젝트 부트스트랩 (mso-repository-setup)

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py \
  --target /path/to/project \
  --name "프로젝트 이름" \
  --id "project-id-01"
```

생성되는 구조:

```
project/
├── agent-context/
│   ├── index/index.yaml
│   ├── workflow/                  # *.abox.ttl = workflow SSOT, *.yaml = migration/edit layer
│   └── work-memory/
│       ├── schema.yaml
│       ├── auditlog/   worklog/
│       ├── track-record/{issue-note, agent-decision, alternatives-record, user-decision, trouble-shooting}/
│       └── insight-record/{episodes, patterns, principles}/
└── .gitignore
```

### 기존 프로젝트 점검

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --check /path/to/project
```

### Hook 등록 (auditlog + worklog 자동 기록)

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --hook /path/to/project
```

`.claude/settings.json` 에 `PostToolUse(Bash·Edit·Write → auditlog)` 와 `Stop(→ worklog)` hook이 등록된다.
Codex 프로젝트에서는 provider를 명시한다.

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --hook /path/to/project --provider codex
```

이 경우 `.codex/scripts/`에 hook 스크립트가 복사되고 `.codex/config.toml`과 `.codex/hooks.json`에
worklog/work-memory-check hook이 등록된다.

---

## 2. Scaffold 정의 (mso-scaffold-design)

`index.yaml` 이 repository 구조의 SSOT다. 모든 모듈·서브디렉토리·참조를 여기에 등록한다.

```bash
SF=~/.claude/skills/mso-scaffold-design/scripts/sf_node.py

# 스키마 확인
python3 $SF show project
python3 $SF show module
python3 $SF show subdir

# 모듈 스캐폴드 생성 (stdout → index.yaml 의 modules: 에 붙여넣기)
python3 $SF scaffold module --id "01.core"

# index.yaml 검증
python3 $SF validate agent-context/index/index.yaml

# 파일시스템과 선언 대조
python3 $SF inventory agent-context/index/index.yaml

# 계층 트리 출력 (sub_index 포함)
python3 $SF tree agent-context/index/index.yaml
```

`index.yaml` 최소 예시:

```yaml
project:
  name: "My Project"
  id: "my-project-01"
  description: "TODO"
  owner: "owner@example.com"
  updated: "2026-05-26"
  version: "0.1.0"
  root_offset: "../.."

modules:
  - id: 01.core
    path: 01.core/
    description: 핵심 로직
    subdirs:
      - path: 00.context/
        role: context
        description: 배경 문서
      - path: 01.scripts/
        role: scripts
        description: 실행 스크립트
    key_files: [README.md]
    status: active
```

---

## 3. Workflow 정의 (mso-workflow-design)

workflow TTL ABox(`*.abox.ttl`)가 SSOT다. 기존 YAML은 편집/마이그레이션 레이어이며, Markdown·Mermaid는 변환 산출물이므로 직접 편집하지 않는다.

```bash
WF=~/.claude/skills/mso-workflow-design/scripts/wf_node.py
WFTTL=~/.claude/skills/mso-workflow-design/scripts/wf_to_ttl.py
WFMIG=~/.claude/skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py

# 스키마 확인
python3 $WF show phase
python3 $WF show step
python3 $WF show decision   # judge 5-level 포함
python3 $WF show validation

# 노드 스캐폴드 생성 (stdout → workflow YAML 에 붙여넣기)
python3 $WF scaffold phase --id "P01.discovery"
python3 $WF scaffold step --id "s-001"
python3 $WF scaffold decision --id "d-001" --judge HITL
python3 $WF scaffold validation --id "v-001"

# workflow YAML 검증
python3 $WF validate agent-context/workflow/workflow-00.yaml

# scaffold 정합성 cross-check
python3 $WF validate agent-context/workflow/workflow-00.yaml \
  --scaffold agent-context/index/index.yaml

# harness manifest 생성 (validation 노드 → CI)
python3 $WF harness-manifest agent-context/workflow/workflow-00.yaml \
  --out ci-manifest.json

# 레거시 YAML → TTL 정본 마이그레이션 / drift check
python3 $WFMIG agent-context/workflow
python3 $WFMIG agent-context/workflow --check
python3 $WFTTL validate agent-context/workflow/workflow-00.yaml
```

workflow YAML 시작점은 `skills/mso-workflow-design/assets/module-workflow-template-00.yaml` 을 복사해 사용한다.

### Mermaid 변환 (관측성, 선택)

```bash
MD=~/.claude/skills/mso-workflow-design/scripts

# 단일 모듈 → 통합 마크다운
python3 $MD/workflow_to_markdown.py agent-context/workflow/workflow-00.yaml

# 전체 시각화 세트 (validate 선행 포함)
python3 $MD/workflow_to_mermaid.py --all
```

---

## 4. Work-Memory 사용 (mso-work-memory)

```bash
export WORKMEM_DIR=./agent-context/work-memory
WM=~/.claude/skills/mso-work-memory/scripts/wm_node.py

# entry 생성
python3 $WM new issue-note \
  --title "timeout 누락 발견" --tags "policy,timeout" --module "01.core"

python3 $WM new agent-decision \
  --title "retry 로직 추가 결정" --tags "retry,resilience"

python3 $WM new alternatives-record \
  --title "재시도 정책 3안 비교" --tags "retry,decision"

python3 $WM new user-decision \
  --title "v2 마감 연기 승인" --tags "schedule"

# 통계
python3 $WM stats

# 검증
python3 $WM validate ./agent-context/work-memory

# 단일 entry 조회
python3 $WM show IN-0001

# 그래프 traversal
python3 $WM graph IN-0001 --depth 2 --direction both
```

### entry 타입 정리

| 타입 | prefix | 저장 위치 |
|------|--------|-----------|
| issue-note | IN | track-record/issue-note/ |
| agent-decision | AD | track-record/agent-decision/ |
| alternatives-record | AR | track-record/alternatives-record/ |
| user-decision | UD | track-record/user-decision/ |
| trouble-shooting | TS | track-record/trouble-shooting/ |
| episode | EP | insight-record/episodes/ |
| pattern | PT | insight-record/patterns/ |
| principle | PR | insight-record/principles/ |
| auditlog | AU | auditlog/ (hook 자동) |
| worklog | WL | worklog/ (hook 자동) |

---

## 5. Hook 동작 확인

hook 등록 후 실제 동작 테스트:

```bash
# auditlog hook 수동 실행
echo '{"tool_name":"Bash","tool_input":{"command":"git status"},"session_id":"test","hook_event_name":"PostToolUse"}' \
  | WORKMEM_DIR=./agent-context/work-memory \
    python3 ~/.claude/skills/mso-work-memory/hooks/auditlog.py

# worklog hook 수동 실행
echo '{"session_id":"test","hook_event_name":"Stop"}' \
  | WORKMEM_DIR=./agent-context/work-memory \
    python3 ~/.claude/skills/mso-work-memory/hooks/worklog.py

# 생성 확인
ls agent-context/work-memory/auditlog/
ls agent-context/work-memory/worklog/
```
