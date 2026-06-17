# 아키텍처 (v0.3.4)

## 스킬 관계

```
사용자 요청
    │
    ▼
mso-orchestration          ← 단일 진입점 · 트리거 매칭 · 라우팅
    │
    ├──> mso-repository-setup    ← 프로젝트 init · hook 등록
    │         │
    │         └── agent-context/ 트리 + .claude/settings.json
    │
    ├──> mso-scaffold-design     ← index.yaml SSOT 관리
    │         │
    │         └── index.yaml (모듈·서브디렉토리·참조 선언)
    │
    ├──> mso-workflow-design     ← workflow YAML 규정 · 검증 · 변환
    │         │
    │         ├── workflow/*.yaml (SSOT)
    │         ├── workflow/diagrams/*.md (Mermaid 변환물)
    │         └── ci-manifest.json (harness-manifest)
    │
    └──> mso-work-memory         ← JSONL entry · 검색 · 그래프
              │
              ├── track-record/ (issue-note, agent-decision, user-decision, trouble-shooting)
              ├── insight-record/ (episodes, patterns, principles)
              ├── auditlog/ (hook 자동 기록)
              └── worklog/ (hook 자동 기록)
```

## 스킬 간 의존 관계

| 방향 | 규칙 |
|------|------|
| `mso-scaffold-design` → `mso-workflow-design` | workflow YAML의 `directories.path` 는 index.yaml 등록 경로만 참조 |
| `mso-workflow-design` → `mso-scaffold-design` | 새 directory role 사용 시 index.yaml에 먼저 등록 |
| `mso-repository-setup` → 전체 | init 이 가장 먼저 실행. agent-context/ 트리 없이는 다른 스킬 동작 불가 |
| hook → `mso-work-memory` | auditlog.py·worklog.py 는 work-memory JSONL 스키마를 따름 |

## 데이터 흐름

```
init.py --target
    → agent-context/ 트리 생성
    → index.yaml 최소 골격 생성
    → work-memory/schema.yaml 복사

init.py --hook
    → .claude/settings.json 에 hook 등록

[Claude Code 세션 중]
    PostToolUse(Bash|Edit|Write)
        → hooks/auditlog.py
        → auditlog/AU-YYYY-MM-DD.jsonl  (append)

    Stop
        → hooks/worklog.py
        → worklog/WL-YYYY-MM-DD.jsonl   (append)

sf_node.py validate index.yaml
    → project 스키마 검증
    → module 스키마 검증 (전역 id unique)
    → subdir 스키마 검증
    → sub_index 계층 재귀 해석 (max depth 3)

wf_node.py validate workflow.yaml
    → phase / step / decision / validation / group 스키마 검증
    → judge 조건 검증 (HITL/HITLFE → owner 필수 등)
    → node id 계층 전역 unique 검증
    → --scaffold 옵션 시 directories.path cross-check

wf_node.py harness-manifest
    → validation 노드 수집
    → ci-manifest.json 생성

wf_to_ttl.py validate workflow.yaml   (그래프 검증 — wf_node 보완)
    → ABox(TTL) 투영
    → pyshacl: 로컬 shape (ABox↔TBox 정합; TBox 는 schemas_to_tbox.py 생성)
    → SPARQL: 비순환(DAG) — 다운스트림 재참조 사이클 차단
    → --index 시 scaffold 경로 멤버십 (wf_node._resolve_scaffold 재사용)
ttl_to_wf.py workflow.abox.ttl        (역방향 ingestion)
    → SHACL+비순환 게이트 통과분만 → YAML 승격

wm_node.py new <type>
    → id 할당 (타입별 시퀀스 또는 시각 기반)
    → JSONL entry 작성
    → zvec 인덱스 대상 (reindex 시 임베딩)
```

## SSOT 원칙

| 산출물 | SSOT | 변환물 |
|--------|------|--------|
| repository 구조 | `index.yaml` | — |
| workflow | `workflow/*.yaml` | `*.md`, Mermaid, **TTL ABox**(`wf_to_ttl` 투영, 검증·그래프용) |
| workflow 스키마(TBox) | `references/schemas/*.yaml` | **`tbox/*.ttl` + `shapes/*.ttl`**(`schemas_to_tbox.py` 생성, drift 가드) |
| work-memory | `*.jsonl` | zvec 인덱스 (재생성 가능) |
| hook 설정 | `.claude/settings.json` | — |

> 워크플로 층위: `global`=UUG(엄브렐러 루트) / `root-workflow`+`sub-workflow`=MSO(프로젝트 내). TTL 은 파생; `ttl_to_wf` 만 SHACL 게이트로 TTL→YAML ingestion 허용.

## Hook 아키텍처

```
.claude/settings.json
    PostToolUse matcher: Bash|Edit|MultiEdit|Write
        → hooks/auditlog.py
            env: WORKMEM_DIR=<절대경로>
            stdin: Claude Code PostToolUse JSON
            출력: auditlog/AU-YYYY-MM-DD.jsonl (append)

    Stop
        → hooks/worklog.py
            env: WORKMEM_DIR=<절대경로>
            stdin: Claude Code Stop JSON
            출력: worklog/WL-YYYY-MM-DD.jsonl (append)
```

## 파일시스템 레이아웃

```
project/
├── agent-context/                     ← MSO 전용 (git에 포함)
│   ├── index/
│   │   └── index.yaml                 ← scaffold SSOT
│   ├── workflow/                       ← workflow YAML 저장소
│   │   ├── workflow-00.yaml           ← 기본 workflow
│   │   └── workflow-<slug>.yaml       ← 추가 workflow
│   └── work-memory/
│       ├── schema.yaml                ← entry 스키마 정의
│       ├── auditlog/                  ← AU-*.jsonl (자동)
│       ├── worklog/                   ← WL-*.jsonl (자동)
│       ├── track-record/
│       │   ├── issue-note/            ← IN-*.jsonl
│       │   ├── agent-decision/        ← AD-*.jsonl
│       │   ├── user-decision/         ← UD-*.jsonl
│       │   └── trouble-shooting/      ← TS-*.jsonl
│       ├── insight-record/
│       │   ├── episodes/              ← EP-*.jsonl
│       │   ├── patterns/              ← PT-*.jsonl
│       │   └── principles/            ← PR-*.jsonl
│       └── .zvec/                     ← 벡터 인덱스 (gitignore)
├── .claude/
│   └── settings.json                  ← hook 설정
└── .gitignore                         ← agent-context/work-memory/.zvec/ 포함
```
