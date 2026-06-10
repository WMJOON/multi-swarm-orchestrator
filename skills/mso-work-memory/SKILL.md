---
name: mso-work-memory
description: >
  프로젝트의 작업 기록을 jsonl + 임베딩 + 그래프 형태로 자산화하는 스킬.
  agent-context/work-memory/ 에 7종 entry (issue-note, agent-decision,
  user-decision, trouble-shooting, episode, pattern, principle) + auditlog/worklog
  를 jsonl 로 보관. zvec 시맨틱 검색 + relations 그래프 traversal 지원.
  다음 상황에서 사용한다:
  (1) 새 이슈·결정·사고·회고 entry 추가,
  (2) 과거 사례 시맨틱 검색 ("비슷한 timeout 사고 있었나?"),
  (3) 그래프 traversal ("이 decision 이 어떤 사고로 이어졌나"),
  (4) 정기 회고 (episode → pattern → principle 추출),
  (5) 자동 hook (session 이벤트 → auditlog jsonl append).
---

# MSO Work Memory

프로젝트의 운영 기록과 인사이트를 jsonl 파일 + zvec 임베딩 + 그래프 relations 로 자산화한다. 단기 운영 흐름 (track-record) 과 장기 자산화 (insight-record) 를 분리.

## 핵심 원리

1. **JSONL 1줄 1 entry** — git diff 친화, 임베딩 입력, append-only
2. **타입별 시퀀스 id** — `IN-0001`, `EP-0042` (zero-pad 4)
3. **공통 스키마** — id, type, title, text, tags, created_at, relations, metadata
4. **그래프 임베드** — `relations: [{type, target}]` 로 entry 간 인과 관계 표현 (별도 DB 불필요)
5. **zvec 시맨틱 검색** — `text` 필드 임베딩, `tags` 필터
6. **선제 기록 책임** — 사용자가 요청하기를 기다리지 말고, 향후 작업·구조에 지속 영향을 주는 결정(UD/AD)·이슈(IN)·해결(TS)을 에이전트가 스스로 판단해 먼저 기록한다. 단발성 지시·사소한 수정·질문은 제외. AD는 대안이 둘 이상이고 득실이 갈릴 때 `metadata.rationale/alternatives/confidence`와 함께 기록하고, 사용자가 채택하면 이어지는 UD를 `followed-by`로 연결한다. *이 행동 규약은 always-on이어야 효과가 있으므로, 프로젝트는 이 책임 항목을 상시 로드되는 rules(CLAUDE.md/AGENTS.md 등)에도 둔다 — 이 스킬은 '어떻게(절차·CLI·스키마)'를 소유한다.*

## 디렉토리 구조 (프로젝트 측)

```
agent-context/work-memory/
├── schema.yaml                 # 프로젝트 로컬 스키마 정의 (이 스킬에서 복제)
├── auditlog/                   # 자동 hook
│   └── YYYY-MM/DD.jsonl
├── worklog/                    # 일상 작업 일지
│   └── YYYY-MM/DD.jsonl
│
├── track-record/               # ── 이슈 1건 라이프사이클 ──
│   ├── issue-note/        IN-NNNN.jsonl
│   ├── agent-decision/    AD-NNNN.jsonl
│   ├── user-decision/     UD-NNNN.jsonl  (structural 태그 = repo-ADR)
│   └── trouble-shooting/  TS-NNNN.jsonl
│
└── insight-record/             # ── 추상화 그래디언트 ──
    ├── episodes/          EP-NNNN.jsonl
    ├── patterns/          PT-NNNN.jsonl
    └── principles/        PR-NNNN.jsonl
```

## Entry 타입 매트릭스

| Prefix | Type | 영역 | 작성 시점 |
|---|---|---|---|
| **IN** | issue-note | track | 문제 발견 즉시 |
| **AD** | agent-decision | track | 에이전트가 판단 내리고 실행할 때 |
| **UD** | user-decision | track | 사용자가 정책·구조 결정 시 (structural 태그 → ADR) |
| **TS** | trouble-shooting | track | 해결 종결 시 (resolution + prevention) |
| **EP** | episode | insight | 사건이 일단락된 후 회고 (TS 다음) |
| **PT** | pattern | insight | EP 여러 개 누적 후 반복 발견 |
| **PR** | principle | insight | PT 안정화 후 응축된 원칙 |
| AU | auditlog | (자동) | hook이 append |
| WL | worklog | (자동/수동) | 일자별 |

## 라이프사이클 그래프

```
IN ──raised──> AD/UD ──followed-by──> ... ──resolved-by──> TS
                                                            │
                                                analyzed-in │
                                                            ▼
                                                            EP
                                              generalized-in │
                                                            ▼
                                                            PT
                                            crystallized-in  │
                                                            ▼
                                                            PR
```

## 공통 jsonl 스키마

```json
{
  "id": "IN-0042",
  "type": "issue-note",
  "title": "한 줄 요약 (≤60자)",
  "text": "본문 (markdown 가능, 임베딩 대상)",
  "tags": ["...", "..."],
  "created_at": "2026-05-22T15:30:00Z",
  "source_path": "agent-context/work-memory/track-record/issue-note/IN-0042.jsonl",
  "author": "user|agent|<agent-id>",
  "relations": [
    {"type": "resolved-by", "target": "TS-0017"}
  ],
  "metadata": {
    "module": "02.AI-Chatbot-Policy",
    "severity": "minor"
  }
}
```

상세 스키마: [references/schema.yaml](references/schema.yaml).

## CLI: `wm_node.py`

```bash
# 새 entry 작성 (대화형 stub 출력)
python wm_node.py new <type> --title "..." [--tags a,b,c] [--related TS-0017:resolved-by]

# 검증 (단일 파일 또는 디렉토리 전체)
python wm_node.py validate <path>

# 시맨틱 검색 (zvec)
python wm_node.py search "비슷한 timeout 사고" [--type episode] [--tag policy]

# 그래프 traversal (특정 entry 의 조상/자손)
python wm_node.py graph <id> [--depth 3] [--direction in|out|both]

# 통계
python wm_node.py stats

# zvec 인덱스 재빌드
python wm_node.py reindex
```

상세 사용법: [references/cli.md](references/cli.md).

## Relation 어휘

| 타입 | 방향 | 용도 |
|---|---|---|
| `raised` | IN → AD/UD | 이슈가 결정을 유발 |
| `followed-by` | AD ↔ UD ↔ TS | 시간 순 다음 |
| `resolved-by` | IN ← TS | 이슈가 해결됨 |
| `caused-by` | TS → IN | 원인 추적 |
| `analyzed-in` | TS → EP | 회고에 포함됨 |
| `shows-pattern` | EP → PT | 패턴 인스턴스 |
| `generalized-in` | EP → PT | 일반화 |
| `crystallized-in` | PT → PR | 원칙으로 응축 |
| `references` | * → * | 단순 참조 |
| `supersedes` | new → old | 대체 |
| `refines` | new → old | 정교화 |
| `depends-on` | * → * | 의존 |

## 기록 판단 넛지 (work-memory-check.sh)

`auditlog`/`worklog` 는 자동 로깅이지만, **track-record/insight-record entry 를 언제 남길지**에 대한 판단 트리거는 별도다. `hooks/work-memory-check.sh` 가 Stop/PreCompact 에서 비차단 넛지를 띄운다:

1. **track 넛지** — "결정 가치 있는" 변경(`WM_WORTHY_PATHS`, 기본=오케스트레이션 레이어)이 work-memory 최신 기록보다 앞서고 기록 대기가 없으면 → UD/AD/IN/TS 작성 권유.
2. **insight 넛지** — 종결된 TS 이후 EP 회고가 없으면 → episode 회고 권유 (EP→PT→PR 추상화 유도).

판단 *기준* 텍스트는 [assets/work-memory-judgment.md](assets/work-memory-judgment.md) 를 프로젝트의 상시 로드 rules(CLAUDE.md/AGENTS.md)에 드롭인한다 — 핵심 원리 6(always-on 위임)과 일치. `mso-repository-setup` 의 `init.py --hook` 가 이 훅을 Stop/PreCompact 에 자동 등록한다.

## Hook 통합 (auditlog 자동)

기존 `mso-agent-audit-log` 의 SessionStart/PreCompact/SessionEnd 훅을 흡수.
`.claude/settings.json` 에 등록:

```json
"hooks": {
  "SessionStart": [{
    "hooks": [{
      "type": "command",
      "command": "WORKMEM_DIR=\"/path/to/project/agent-context/work-memory\" bash \"~/.claude/skills/mso-work-memory/hooks/session_start_hook.sh\"",
      "timeout": 10
    }]
  }],
  "SessionEnd": [{...}]
}
```

## Cross-Skill 관계

| Skill | 관계 |
|---|---|
| **mso-scaffold-design** | work-memory 디렉토리가 scaffold(index.yaml) 에 등록되어 있어야 함. |
| **mso-workflow-design** | workflow 의 decision/validation 노드 변경 시 UD entry 자동 생성 권장. |
| **simple-knowledge-zvec** | 본 스킬의 zvec 인덱싱 기반 라이브러리. |

## 의존성

```
pyyaml>=6.0
# zvec 검색 사용 시
zvec  (simple-knowledge-zvec 스킬 통해)
```

## 참고 자료

- [references/schema.yaml](references/schema.yaml) — 공통 jsonl 스키마
- [references/cli.md](references/cli.md) — wm_node.py 상세 사용법
- [references/lifecycle.md](references/lifecycle.md) — track → insight 흐름 가이드
- [scripts/wm_node.py](scripts/wm_node.py) — CLI 도구
- [assets/templates/](assets/templates/) — 타입별 entry 템플릿
