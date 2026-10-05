# 아키텍처 (v0.13.0)

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
    ├──> mso-scaffold-design     ← index.yaml SSOT 관리 + workflow 경로·locator 참조 점검
    │         │
    │         ├── index.yaml (모듈·서브디렉토리·참조 선언)
    │         └── check_artifact_index.py (workflow 참조 ↔ index·registry 매핑, 읽기 전용)
    │
    ├──> mso-workflow-design     ← workflow TTL ABox 정본 · YAML 마이그레이션 · 검증 · 변환
    │         │
    │         ├── workflow/*.abox.ttl (SSOT)
    │         ├── index/artifacts.abox.ttl (artifact 층 SSOT, v0.13.0: 개념 + 규약 버전)
    │         ├── validate_artifact_layer.py (SHACL/SPARQL + 규약 불변 + 파일 스캔)
    │         ├── references/queries/artifact-lineage.rq (artifact 계보)
    │         ├── pattern_to_workflow_draft.py (절차형 pattern → draft workflow)
    │         ├── workflow/*.yaml (legacy/edit layer)
    │         ├── workflow/diagrams/*.md (Mermaid 변환물)
    │         └── ci-manifest.json (harness-manifest)
    │
    ├──> mso-work-memory-link    ← 연관 저장소(서브모듈·별도 경로) work-memory 설정·점검 (v0.13.0)
    │         │
    │         └── work-memory/linked-repos.yaml + wm_node.py --repo/--repo-name
    │
    └──> mso-work-memory         ← JSONL entry · 검색 · 그래프
              │
              ├── track-record/ (issue-note, agent-decision, alternatives-record, user-decision, trouble-shooting)
              ├── insight-record/ (episodes, patterns, principles)
              ├── auditlog/ (hook 자동 기록)
              └── worklog/ (workflow TTL node 실행 기록)
```

## 스킬 간 의존 관계

| 방향 | 규칙 |
|------|------|
| `mso-scaffold-design` → `mso-workflow-design` | workflow YAML의 `directories.path` 는 index.yaml 등록 경로만 참조 |
| `mso-workflow-design` → `mso-scaffold-design` | 새 directory role 사용 시 index.yaml에 먼저 등록 |
| `mso-workflow-design` → `mso-scaffold-design` (artifact 층) | artifact 규약의 `wf:inModule`/디렉토리 접두부는 index.yaml의 module 경로 아래여야 한다(교차 층 점검) |
| `mso-work-memory-link` → `mso-work-memory` | 등록·해석은 `wm_repos.py`, 기록은 `wm_node.py --repo`, 커밋은 `commit-work-memory.sh`(훅) |
| `mso-repository-setup` → 전체 | init 이 가장 먼저 실행. agent-context/ 트리 없이는 다른 스킬 동작 불가 |
| hook → `mso-work-memory` | auditlog.py 는 도구 실행을 자동 기록하고, commit-work-memory.sh 는 work-memory 변경분만 커밋 |

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

    Stop / PreCompact
        → hooks/commit-work-memory.sh
        → work-memory 변경분만 커밋 (worklog 자동 생성 없음)

    SessionStart(compact/resume)
        → hooks/work-memory-check.sh
        → AD/IN/TS/worklog 기록 필요성 넛지

sf_node.py validate index.yaml
    → project 스키마 검증
    → module 스키마 검증 (전역 id unique)
    → subdir 스키마 검증
    → sub_index 계층 재귀 해석 (max depth 3)

wf_node.py validate workflow.yaml
    → workflow / step / decision / eval / group 스키마 검증
    → judge 조건 검증 (HITL/HITLFE → owner 필수 등)
    → node id 계층 전역 unique 검증
    → --scaffold 옵션 시 directories.path cross-check

wf_node.py harness-manifest
    → harness 보유 eval 노드 수집
    → ci-manifest.json 생성

wm_node.py new <type>
    → id 할당 (타입별 시퀀스 또는 시각 기반)
    → JSONL entry 작성
    → zvec 인덱스 대상 (reindex 시 임베딩)
```

## SSOT 원칙

| 산출물 | SSOT | 변환물 |
|--------|------|--------|
| repository 구조 | `index.yaml` | — |
| workflow | `workflow/*.abox.ttl` | `*.yaml`(편집층), `*.md`, Mermaid 다이어그램 |
| work-memory | `*.jsonl` | zvec 인덱스 (재생성 가능) |
| hook 설정 | `.claude/settings.json` | — |

## Hook 아키텍처

```
.claude/settings.json
    PostToolUse matcher: Bash|Edit|MultiEdit|Write
        → hooks/auditlog.py
            env: WORKMEM_DIR=<절대경로>
            stdin: Claude Code PostToolUse JSON
            출력: auditlog/AU-YYYY-MM-DD.jsonl (append)

    Stop / PreCompact
        → hooks/commit-work-memory.sh
            env: WORKMEM_DIR=<절대경로>
            출력: 없음. work-memory 변경분만 커밋.
            v0.13.0: linked-repos.yaml 에서 autocommit: true 인 연관 저장소의 work-memory도
                     각자의 git 에서 커밋한다(push 없음, 서브모듈 포인터 불변, MSO_WM_LINKED=0 으로 끔).

    SessionStart (compact/resume)
        → hooks/work-memory-check.sh
            v0.13.0: 연관 저장소에 work-memory 최신 기록 이후의 작업 흔적이 있으면 넛지
```

세션의 프로젝트 루트(`CLAUDE_PROJECT_DIR`) 훅은 루트 work-memory만 본다. 서브모듈 work-memory는 별도 git 저장소이므로
`linked-repos.yaml`에 등록해야 커밋된다(발견만 된 서브모듈은 `autocommit: false`).

## 파일시스템 레이아웃

```
project/
├── agent-context/                     ← MSO 전용 (git에 포함)
│   ├── index/
│   │   ├── index.yaml                 ← scaffold SSOT (디렉토리 층)
│   │   └── artifacts.abox.ttl         ← artifact 층 SSOT (v0.13.0, 선택)
│   ├── workflow/                       ← workflow TTL ABox 정본 + YAML 편집층
│   │   ├── workflow-00.yaml           ← 기본 workflow
│   │   └── workflow-<slug>.yaml       ← 추가 workflow
│   └── work-memory/
│       ├── schema.yaml                ← entry 스키마 정의
│       ├── linked-repos.yaml          ← 연관 저장소 등록부 (v0.13.0, 선택)
│       ├── auditlog/                  ← AU-*.jsonl (자동)
│       ├── worklog/                   ← WL-*.jsonl (workflow TTL node 실행 기록)
│       ├── track-record/
│       │   ├── issue-note/            ← IN-*.jsonl
│       │   ├── agent-decision/        ← AD-*.jsonl
│       │   ├── alternatives-record/   ← AR-*.jsonl
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


## Repository Graph (v0.7.0)

> Repository는 파일을 저장하는 곳이 아니라, 실행(Execution)과 산출물(Artifact)의
> 관계를 저장하는 그래프다.

```text
Repository Graph
├── Execution Graph        (Control Plane — wf:Rail)
│     Node: Workflow · Execution(Task|Decision|Eval) · Terminal(Start|End)
│     Rail: default · reads · delegates_to · escalates_to
│           measured_by · measures · evolves_to · tests_to
└── Artifact Stream Graph  (Data Plane — wf:Stream)
      Node: Artifact  (Artifact First — Document/Prompt/Policy/Ontology/KB/DB 전부)
      Stream: consumed_by · produces_to · evidence_of
```

- edge는 reify된 일급 인스턴스다 (`wf:from`/`wf:to`/`railType`/`streamType`).
- 모든 Execution은 `hasSubject`(기본 self)를 가진다. 주체 전환은 hand_off rail
  (`delegates_to`/`escalates_to`)이며 workflow 형태는 바뀌지 않는다.
- Eval의 평가 단위는 WorkflowGraph closure(소비 Artifact + Execution + 생산 Artifact)다.
- 저장 관계와 추론 관계를 구분한다: `consumed_by ∘ produces_to = evidence_of`는
  materialize가 파생하고 `wf:derived`로 표시한다.
- Trust는 저장하지 않는다 — Trust Policy로 계산하고 리포트로만 낸다.

### v0.7 도구 체인 (hook: workflow-check.sh)

```text
*.abox.ttl 저장
  → validate_abox.py    (SSOT shape/oracle/partition/loop 검증 — 설계 게이트)
  → materialize_v07.py  (property chain 파생 → *.inferred.ttl)
  → trust_v07.py        (Trust 계산 → observability/trust-report.md)
  → observe_graph.py    (v0.7 native 렌더 → observability/graph/)
```

### 관측 출력 규약

```text
agent-context/observability/          # 분석 리포트
├── artifact-stream-report.md · workflow-ssot-report.md
├── runtime-analysis.md · trust-report.md
└── graph/                            # 시각화 md
    ├── README.md · workflow-subgraph-index.md · oracle-graph.md
    ├── class-layer-map.md · property-map.md
    └── <scope>/{repository,workflow,artifact-stream}-graph.md
```

## Artifact 층 (v0.13.0)

SSOT는 두 층으로 나뉜다. 디렉토리 층(`index.yaml`, 모듈과 서브디렉토리)과 artifact 층(`artifacts.abox.ttl`, 이름 규약·형식·디렉토리 템플릿·소비자 유형)이며
둘을 잇는 것은 `wf:inModule`(임시 문자열) 하나다. artifact 층은 개념(안정 IRI)과 규약 버전(유효 구간)으로 다시 나뉜다.

```
workflow ABox  --wf:Stream-->  art:<name>  (개념, 안정 IRI)  --wf:hasConvention-->  art:<name>_cN  (규약 버전)
  Execution                      유형, consumerType, 설명                              directoryTemplate / namingConvention / fileFormat
  consumed_by / produces_to      (producer/consumer는 Stream에서 도출)                  변수, 메타데이터, validFrom / validUntil
```

- 검증: SHACL/SPARQL(`workflow-artifact-layer-shapes.ttl`) + 파이썬 보조(교차 층, git HEAD 기준 규약 불변, 파일 스캔).
- 계보: 변형 파일은 별도 artifact이고 Execution의 소비·생산 Stream이 이를 잇는다. `artifact-lineage.rq`로 조회한다.
- PROV-O: 어휘 정본은 `wf:`이고 정렬은 TBox 주석으로만 둔다(D-23, D-23a). 설계 단계의 Execution/Artifact는 P-Plan의 Step/Variable에,
  실행 기록은 `prov:Activity`/`prov:Entity`에 대응한다. 상세는 [artifact-model.md](artifact-model.md).

