---
name: mso-work-memory
description: >
  프로젝트의 작업 기록을 jsonl + 임베딩 + 그래프 형태로 자산화하는 스킬.
  agent-context/work-memory/ 에 9종 entry (issue-note, agent-decision,
  user-decision, alternatives-record, trouble-shooting, release-note,
  episode, pattern, principle) + auditlog/worklog 를 jsonl 로 보관.
  zvec 시맨틱 검색 + relations 그래프 traversal +
  TTL projection/SHACL validation 지원.
  다음 상황에서 사용한다:
  (1) 새 이슈·결정·사고·회고 entry 추가,
  (2) 과거 사례 시맨틱 검색 ("비슷한 timeout 사고 있었나?"),
  (3) 그래프 traversal ("이 decision 이 어떤 사고로 이어졌나"),
  (4) 정기 회고 (episode → pattern → principle 추출),
  (5) 자동 hook (session 이벤트 → auditlog jsonl append),
  (6) 릴리스 기록 + 교훈 유효성 추적 ("이 UD/원칙이 v0.7.0 에서도 유효한가?",
      release-note + verified-in/invalidated-by/rolls-back),
  (7) 실행 시점 context pack 검색 — workflow node/자유 질의로 연관 기억 호출
      (wm_context.py, lexical, zvec 불필요; "context pack", "연관 기억 호출").
  (8) Antigravity provider 지원 — hooks/adapter_antigravity.py 가 Antigravity 의
      camelCase hooks.json(PostToolUse/Stop/PreInvocation) 을 기존 snake_case
      훅 계약으로 변환한다 (등록은 mso-repository-setup 담당).
metadata:
  version: "0.11.0"
---

# MSO Work Memory

프로젝트의 운영 기록과 인사이트를 jsonl 파일 + zvec 임베딩 + 그래프 relations 로 자산화한다. 단기 운영 흐름 (track-record), 상태 축 (release-record), 장기 자산화 (insight-record) 를 분리한다. JSONL은 append-only SSOT이고, TTL은 관계/라이프사이클 검증을 위한 projection layer다.

## 핵심 원리

1. **JSONL 1줄 1 entry** — git diff 친화, 임베딩 입력, append-only
2. **타입별 시퀀스 id** — `IN-0001`, `EP-0042` (zero-pad 4)
3. **공통 스키마** — id, type, title, text, tags, created_at, relations, metadata
4. **그래프 임베드** — `relations: [{type, target}]` 로 entry 간 인과 관계 표현 (별도 DB 불필요)
5. **zvec 시맨틱 검색** — `text` 필드 임베딩, `tags` 필터
6. **TTL projection + SHACL gate** — curated JSONL(track/insight)을 TTL ABox로 투영해 `resolved-by`, `caused-by`, `analyzed-in` 같은 relation target 타입을 검증한다. `references`는 entry id뿐 아니라 파일 경로 같은 외부 참조도 `ExternalReference`로 허용한다.
7. **선제 기록 책임** — 사용자가 요청하기를 기다리지 말고, 향후 작업·구조에 지속 영향을 주는 결정(UD/AD)·이슈(IN)·해결(TS)을 에이전트가 스스로 판단해 먼저 기록한다. 단발성 지시·사소한 수정·질문은 제외. **결정 권한으로 갈래**: 에이전트가 *권한 내에서 스스로 결정·실행*하면 AD(`metadata.rationale/alternatives/confidence`). 대안이 둘 이상이고 득실이 갈려 *상위 권위(oracle = user 또는 metric)에 올려 판단받아야* 하면 AR(`metadata.provided_by/options/recommended`)로 기록하고, 채택 시 이어지는 UD를 `followed-by`로 연결한다(AR→UD). 즉 "사용자가 채택하는 옵션 제시"는 AD 가 아니라 AR. **IN/TS는 회고 기록이 정상이다** — UD는 사용자 발화라는 외부 트리거가 있어 잘 남지만, IN/TS는 에이전트 내부 작업에서만 촉발돼 누락되기 쉽다. 테스트 green·fix 검증·`fix:`/`revert:` 커밋·접근 전환을 IN/TS 기록 앵커로 삼고, 같은 턴에 발견+해결했다면 IN+TS를 함께 회고로 남긴다(TS 단독 금지 — 원인 추적이 끊긴다). *이 행동 규약은 always-on이어야 효과가 있으므로, 프로젝트는 이 책임 항목을 상시 로드되는 rules(CLAUDE.md/AGENTS.md 등)에도 둔다 — 이 스킬은 '어떻게(절차·CLI·스키마)'를 소유한다.*

## 디렉토리 구조 (프로젝트 측)

모든 영역이 **append-only JSONL**(한 줄 = 한 entry)이다. track/insight 는 타입별
aggregate 파일 1개에 누적한다 — `.jsonl` 의미론을 auditlog/worklog 와 일관화 (schema v1.2.0).
entry 식별자는 파일 경로가 아니라 **record 내부의 `id` 필드**(primary key)다.

```
agent-context/work-memory/
├── schema.yaml                 # 프로젝트 로컬 스키마 정의 (이 스킬에서 복제)
├── graph/
│   └── work-memory.abox.ttl     # JSONL에서 생성한 관계 검증/관측용 projection
├── auditlog/                   # 자동 hook
│   └── AU-YYYY-MM-DD.jsonl
├── worklog/                    # workflow TTL node 실행 기록 (수동 — wm_node.py new)
│   └── WL-YYYY-MM-DD.jsonl
│
├── track-record/               # ── 이슈 1건 라이프사이클 (타입별 aggregate) ──
│   ├── issue-note.jsonl          (IN-NNNN …)
│   ├── agent-decision.jsonl      (AD-NNNN …)
│   ├── user-decision.jsonl       (UD-NNNN … structural=repo-ADR / boundary=drift 추적)
│   ├── alternatives-record.jsonl (AR-NNNN … 결정 전 옵션+득실, AR→UD)
│   └── trouble-shooting.jsonl    (TS-NNNN …)
│
├── release-record/             # ── 상태 축: 릴리스 타임라인 (타입별 aggregate) ──
│   └── release-note.jsonl        (RN-NNNN … version/released_at/kind, current 는 derived)
│
└── insight-record/             # ── 추상화 그래디언트 (타입별 aggregate) ──
    ├── episode.jsonl             (EP-NNNN …)
    ├── pattern.jsonl             (PT-NNNN …)
    └── principle.jsonl           (PR-NNNN …)
```

> **마이그레이션**: 구버전(v1.1.x)은 `track-record/<type>/<ID>.jsonl` per-entry 파일이었다.
> `scripts/wm_migrate.py`(dry-run 기본, `--apply`)로 타입별 aggregate 로 합치고 원본은
> `.migration-archive/` 로 옮긴다. reader(validate/show/graph/stats/ttl)는 신/구를 모두
> 읽지만 **같은 트리 안 공존은 DUP-ID 를 유발**하므로 마이그레이션 후 archive 가 필수다.

## 연관 저장소 work-memory (버전 미지정, v0.10.1 이후 변경)

한 세션이 프로젝트 루트(예: 엄브렐러 repo)에서 열려도 하위 저장소(서브모듈)나 별도 경로의 MSO 저장소에서 일할 수 있다. 훅은 `CLAUDE_PROJECT_DIR` 하나만 대상으로 하므로, 그 저장소 work-memory 에는 기록도 커밋도 되지 않던 공백을 메운다.

**등록부** `<root>/agent-context/work-memory/linked-repos.yaml` (선택):

```yaml
discover_gitmodules: true          # 기본 true. .gitmodules 서브모듈 중 work-memory 가 있는 곳을 자동 발견
linked_repos:
  - name: child-repo        # --repo-name 으로 부르는 이름
    path: child-repo        # 절대, ~, 또는 루트 기준 상대
    autocommit: true               # Stop 훅이 이 저장소 work-memory 를 자동 커밋 (기본 false)
  - name: mso
    path: ~/path/to/another-repo
```

- 자동 발견된 서브모듈은 `autocommit: false`다. 켜려면 같은 `path` 로 항목을 두고 `autocommit: true` 를 준다(등록부 항목이 이긴다). 없는 경로는 조용히 건너뛴다.
- **기록**: `wm_node.py <명령> --repo <경로>` 또는 `--repo-name <이름>`(위치 무관). 대상 저장소의 `schema.yaml` 로 어휘와 검증을 한다. `WORKMEM_DIR` 보다 우선한다.
- **커밋**: `commit-work-memory.sh` 가 루트에 더해 `autocommit: true` 저장소의 work-memory 를 각자의 git 에서 커밋한다. work-memory 경로만 stage 하고 push 하지 않으며 서브모듈 포인터는 건드리지 않는다. `MSO_WM_LINKED=0` 으로 이 확장만 끈다.
- **넛지**: `work-memory-check.sh` 는 SessionStart 에서, 연관 저장소의 work-memory 최신 기록보다 나중에 바뀐 파일이 있으면 어느 저장소에 기록이 필요할 수 있는지 알린다. 파일 수정 시각 기준이라 체크아웃·풀로 바뀐 파일도 흔적으로 센다(오탐 가능).
- 해석기: `scripts/wm_repos.py list|resolve`. 시험: `tests/test_linked_repos.py`.

## Entry 타입 매트릭스

| Prefix | Type | 영역 | 작성 시점 |
|---|---|---|---|
| **IN** | issue-note | track | 문제 발견 즉시 |
| **AD** | agent-decision | track | 에이전트가 **결정 권한 내에서** 판단 내리고 즉시 실행할 때 |
| **AR** | alternatives-record | track | 에이전트/사용자가 **상위 권위(oracle)에 옵션을 올릴 때** (결정 전, 옵션+득실) |
| **UD** | user-decision | track | 사용자가 정책·구조 결정 시 (structural 태그 → ADR / boundary → drift 추적) |
| **TS** | trouble-shooting | track | 해결 종결 시 (resolution + prevention) |
| **RN** | release-note | release | 릴리스/롤백 시점 (version + kind, current 는 derived) |
| **EP** | episode | insight | 사건이 일단락된 후 회고 (TS 다음) |
| **PT** | pattern | insight | EP 여러 개 누적 후 반복 발견 |
| **PR** | principle | insight | PT 안정화 후 응축된 원칙 |
| AU | auditlog | (자동) | hook이 append |
| WL | worklog | (수동) | workflow TTL node 실행 결과 기록 시 |

## 라이프사이클 그래프

```
IN ──raised──> AD                    (agent 권한 내 결정·실행)
IN ──raised──> AR ──followed-by──> UD (oracle 에게 옵션 제시 → 결정)
IN ──raised──> AD/UD ──followed-by──> ... ──resolved-by──> TS ──released-in──> RN
                                                            │                   │
                                                analyzed-in │        rolls-back │ (롤백 시 새 RN)
                                                            ▼                   ▼
                                                            EP                  RN′
                                              generalized-in │
                                                            ▼
                                                            PT      UD/AD/TS/PT/PR ──verified-in────> RN
                                            crystallized-in  │      UD/AD/TS/PT/PR ──invalidated-by─> RN
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
  "source_path": "agent-context/work-memory/track-record/issue-note.jsonl",
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

상세 스키마: [references/schema.yaml](references/schema.yaml). 타입별 `metadata` 권장 필드(AR 의 `options`/`recommended`, RN 의 `version`/`kind` 등)는 `wm_node.py new` 의 `--meta key=value`(스칼라, 반복) 또는 `--metadata '<json>'`(리스트·중첩)으로 채운다. `--meta` 는 semver·식별자 보존을 위해 값을 JSON 파싱하지 않고 `true`/`false`/`null` 만 리터럴로 변환한다.

## 의사결정 거버넌스 컨벤션 (v0.5.0)

척추 원리 — **Deliberation is a View**: 코어는 이벤트(IN/AR/AD/UD)와 관계만 저장한다. "의사결정 케이스"·"drift 사건"은 별도 노드로 저장하지 않고 그래프에서 **쿼리로 재구성되는 view** 다.

- **AD vs AR 구분** — *agent 가 결정 권한을 갖고 즉시 실행* → **AD**. *agent 가 상위 권위(oracle = user 또는 metric/KPI)에 옵션을 올림* → **AR**. AR 은 결정하지 않으며, 채택 시 `followed-by` 로 UD 에 연결한다. (프로젝트가 oracle-strict 면 AD 비활성화는 schema 선택사항.)
- **oracle ∈ {human, metric}** — 결정 권위는 사람만이 아니다. eval 대조가 지표 기반이면 metric/KPI 게이트도 oracle 이다.
- **DriftEvent = derived** — drift 는 노드가 아니라, 같은 `UD.boundary` 의 시간순 체인에 형성되는 `supersedes`/`refines` 링크다. 그 링크 자체가 drift event.
- **DecisionCase = view → episode** — 진행 중 케이스는 IN 을 root 로 한 traversal subgraph(view)다. 종결 시 회고로 결정화하면 기존 `episode`(EP) 가 그 envelope — 신규 타입을 만들지 않는다.
- **policy → stale 캐스케이드** — 코어는 "UD.boundary + supersedes=drift event" 신호까지만 책임진다. drift→stale 재처리 큐의 *구현*은 산출물 모델에 의존하므로 프로젝트 영역(레퍼런스 패턴).

## 릴리스·유효성 거버넌스 (v0.7.0)

교훈(UD/AD/TS)과 인사이트(PT/PR)는 특정 시점의 코드/구조를 전제로 성립한다. 릴리스가 그 전제를 바꾸면 "어떤 교훈이 더 이상 동작하지 않는가"를 추적할 수 있어야 한다. `release-note`(RN) 가 그 상태 축의 앵커다.

- **RN = 상태 앵커** — `metadata.version`(semver), `released_at`, `kind: release|rollback`, `scope` 를 기록한다. `IN → TS → RN` 체인으로 "이 해결이 어느 릴리스에 실렸나"가 이어진다 (`TS ──released-in──> RN`).
- **current 는 derived view — 저장 금지** — "현재 버전" 플래그를 RN 필드로 두면 릴리스마다 이전 entry 를 고쳐야 해서 append-only 가 깨진다. current = *rollback 이 아니고 rolls-back 의 대상도 아닌 RN 중 `released_at` 최신* 으로 쿼리 도출한다 (v0.5.0 "Deliberation is a View" 와 동일 원리).
- **rollback = 이벤트** — 롤백은 기존 RN 을 수정하지 않는다. `kind=rollback` 인 새 RN 을 append 하고 `rolls-back ──> RN(이전)` 엣지로 연결한다.
- **유효성 엣지 쌍** — `verified-in`(이 릴리스 시점에도 유효함 확인, 긍정)과 `invalidated-by`(이 릴리스로 더 이상 성립 안 함, 부정)를 UD/AD/TS/PT/PR 에서 RN 으로 건다. 엣지가 없으면 "유효 추정"이고, 마지막 `verified-in` 대상 RN 이 그 교훈의 검증 신선도다.
- **롤백 캐스케이드도 derived** — 롤백된 RN 을 target 으로 한 `invalidated-by` 엣지는 삭제하지 않는다. "target RN 이 rolls-back 당했다" 는 사실에서 해당 무효화가 *보류 상태(재유효 후보)* 임이 그래프에서 도출된다.
- **PR.status 와의 관계** — `principle.metadata.status=deprecated` 는 사람이 요약한 결론이고, `invalidated-by` 엣지가 그 근거 트레일이다. deprecated 전환 시 근거 RN 엣지를 함께 남긴다.

> **타입 어휘는 schema-driven (v0.3.4+).** `wm_node.py` 는 타입 prefix/dir 과 relation 어휘를 `WORKMEM_DIR/schema.yaml` 의 `types:`/`relation_types:` 에서 읽는다(없으면 기본 7타입 fallback — 하위호환). 같은 엔진을 다른 스코프(예: user-memory UC/UP/UF)로 재사용하려면 그 스코프의 `schema.yaml` 에 `types:` 만 다르게 둔다.

## CLI: `wm_node.py`

```bash
# 새 entry 작성 (대화형 stub 출력)
python wm_node.py new <type> --title "..." [--tags a,b,c] [--related TS-0017:resolved-by]

# 타입별 metadata 지정 — 스칼라는 --meta key=value (반복), 리스트/중첩은 --metadata JSON
python wm_node.py new release-note --title "v0.10.0" --tags release \
    --meta version=0.10.0 --meta kind=release --meta scope=00_multi-swarm-orchestrator
python wm_node.py new alternatives-record --title "..." --tags decision \
    --metadata '{"provided_by":"agent","recommended":1,"options":[{"n":1,"name":"A","trade_off":"..."}]}'

# 검증 (단일 파일 또는 디렉토리 전체)
python wm_node.py validate <path>

# TTL projection 생성 + SHACL 검증
python wm_to_ttl.py project agent-context/work-memory
python wm_to_ttl.py validate agent-context/work-memory --ttl-out agent-context/work-memory/graph/work-memory.abox.ttl

# 시맨틱 검색 (zvec)
python wm_node.py search "비슷한 timeout 사고" [--type episode] [--tag policy]

# 그래프 traversal (특정 entry 의 조상/자손)
python wm_node.py graph <id> [--depth 3] [--direction in|out|both]

# 기존 entry 에 relation 추가 — target 이 나중에 생기는 엣지 확정용
python wm_node.py relate AR-0002 followed-by UD-0015
python wm_node.py relate UD-0015 verified-in RN-0003

# 통계
python wm_node.py stats

# zvec 인덱스 재빌드
python wm_node.py reindex
```

## CLI: `wm_context.py` (런타임 Context Pack, v0.8.0)

mono/umbrella-repo 에서 workflow 가 많아지면 task 수행 시 스코프 밖 기록이 스코프 안 기록을 밀어내는 문제가 생긴다. `wm_context.py` 는 **workflow node id 또는 자유 질의를 받아 연관 entry 를 lexical 랭킹으로 반환하는 런타임 호출 스크립트**다. mso-workflow-optimizer 의 컴파일 타임 ContextPack 과 같은 로직을 쓰며, **스코어링 정본은 이 스크립트다** (optimizer 가 이 모듈을 로드해 재사용).

```bash
# node 모드 — TTL 에서 label/instruction/phase 를 selector 재료로 해석 (rdflib 필요)
python wm_context.py node --node development-s-001 \
    --ttl agent-context/workflow/root-workflow.abox.ttl

# node 모드 (TTL 없이) — node id 만 tag+query seed 로 쓰는 저비용 경로 (rdflib 불필요)
python wm_context.py node --node development-s-001

# query 모드 — workflow 레일 밖 execution 단위
python wm_context.py query "compile step timeout 재발 사례" --module mso-workflow-optimizer --json
```

- **하드 필터 vs 소프트 부스트** — `--filter-tag`(반복, AND)/`--filter-module` 은 스코어링·relation 확장 **이전에** 풀을 자르는 하드 필터다. 스코프 밖 entry 가 높은 스코어나 relation 을 타고 재진입할 수 없다 — mono-repo 오염의 핵심 차단점. `--tags`/`--module` 은 selector tags 에 더해 랭킹만 올리는 소프트 부스트.
- **umbrella-repo** — `--extra-root <path>` (반복) 로 다른 프로젝트의 work-memory 루트를 병합. id 충돌은 first-seen-wins (메인 루트 우선).
- **랭킹** — lexical 전용 (타입 우선순위 + 18×태그 교집합 + 토큰 매치 + module 보너스). zvec 불필요 — `search` 명령과 달리 인덱스 없이 동작한다.
- **가중치 감각** — 태그 1개 교집합 = 18점, 타입 우선순위 = 12~30점, 토큰 매치 = 개당 1점이다. 즉 **자유 텍스트 매치만으로는 타입 격차를 넘지 못한다.** 타입을 가로지르는 랭킹을 원하면 `--tags` 로 잡아야 한다. 토큰화는 ASCII 3자·한글 2자 이상을 잡지만, 한국어는 교착어라 조사가 붙으면 다른 토큰이 되므로(`결정` ≠ `결정을`) ASCII id 태그 병용이 여전히 안정적이다.
- **출력** — plain 은 컨텍스트 주입용 컴팩트 블록, 빈 결과면 무출력·exit 0 (hook 안전). `--json` 은 항상 유효한 pack (`entries: []` 포함) — 기계 소비용.
- 공통 플래그: `--include-types` (기본 8종 curated 타입, `all`=게이트 해제), `--top-k 5`, `--relation-depth 1`, `--max-entry-chars 1200`, `--root` (WORKMEM_DIR 오버라이드).

### workflow cursor 와 자동 주입 (UD-0015)

비-컴파일 실행 경로(에이전트가 TTL 을 직접 따라가는 경우)에서는 **cursor** 가 "지금 어느 node 를 수행 중인가"를 들고, `UserPromptSubmit` 훅이 매 발화마다 그 node 의 pack 을 주입한다. 검색 키는 사용자 발화가 아니라 **workflow 실행 위치**다.

```bash
python wm_context.py cursor set development-s-001 --ttl agent-context/workflow/root-workflow.abox.ttl
python wm_context.py cursor show     # 없으면 무출력
python wm_context.py cursor clear    # node 이탈 시
```

- **cursor 위치**: `.mso/state/workflow-cursor.json` — provider-neutral gitignore 대상. v0.10.0의 `.claude/state/workflow-cursor.json`은 읽기·삭제 fallback으로 지원한다. 가변 상태이므로 append-only JSONL에 두지 않는다.
- **훅**: `hooks/workflow-context-hook.py` (`UserPromptSubmit`, Claude/Codex 공통). cursor가 없으면 무출력이다. `MSO_WORKFLOW_CONTEXT_TOP_K`(기본 3), `MSO_WORKFLOW_CONTEXT_DISABLED=1`.
- **판단은 없어지지 않고 분할상환된다** — cursor 를 쓰려면 'node 진입'을 이미 알아야 한다. 대신 한 번 쓰면 그 node 에 머무는 이후 턴은 자동으로 받는다.
- **왜 PreToolUse 가 아닌가**: plain stdout 이 모델에 주입되는 이벤트는 `SessionStart`/`UserPromptSubmit` 뿐이다. PreToolUse 는 tool 을 차단해야만 모델에 닿고 타이밍도 결정 이후여서 provisioning 에 부적합 (AR-0002 에서 기각, 향후 drift guard 로 분리).
- 컴파일된 LangGraph 경로는 cursor 가 불필요하다 — `_run_node` 가 node 진입 시 pack 을 `active_context` 에 붙인다.

## CLI: `wm_release.py` (release derived view, v0.7.0)

상태(current/rollback 캐스케이드)는 저장하지 않으므로, 이 CLI가 JSONL 에서 매번 도출한다. stdlib 만 사용 — copy-form hook 배포를 위해 wm_node.py 와 독립이다.

```bash
# 현재 릴리스 도출 (rollback 이 아니고 rolls-back 대상도 아닌 RN 중 released_at 최신)
python wm_release.py current [--json]

# 유효성 엣지 상태 (active = 무효화 유효 / suspended = target RN 롤백됨 → 재유효 후보)
python wm_release.py validity [--id UD-0003] [--json]

# session hook 주입용 컴팩트 블록 (RN 이 하나도 없으면 무출력)
python wm_release.py context
```

TTL projection 쪽에는 동일 view 의 SPARQL 정의가 [references/queries/](references/queries/) 에 있다 — `release-current.rq`, `release-invalidated-active.rq`, `release-revalidation-candidates.rq`. JSONL 스크립트와 SPARQL 은 같은 파생 규칙의 두 구현이며, 결과가 일치해야 한다.

상세 사용법: [references/cli.md](references/cli.md).

## Relation 어휘

| 타입 | 방향 | 용도 |
|---|---|---|
| `raised` | IN → AD/UD | 이슈가 결정을 유발 |
| `followed-by` | AD ↔ UD ↔ TS | 시간 순 다음 |
| `resolved-by` | IN ← TS | 이슈가 해결됨 |
| `caused-by` | TS → IN | 원인 추적 |
| `released-in` | TS/UD/AD → RN | 해결·변경이 릴리스에 포함됨 |
| `verified-in` | UD/AD/TS/PT/PR → RN | 이 릴리스 시점에도 유효함 확인 |
| `invalidated-by` | UD/AD/TS/PT/PR → RN | 이 릴리스로 더 이상 성립 안 함 |
| `rolls-back` | RN → RN | 롤백 이벤트 (kind=rollback RN 이 이전 RN 을 되돌림) |
| `analyzed-in` | TS → EP | 회고에 포함됨 |
| `shows-pattern` | EP → PT | 패턴 인스턴스 |
| `generalized-in` | EP → PT | 일반화 |
| `crystallized-in` | PT → PR | 원칙으로 응축 |
| `references` | * → * | 단순 참조 |
| `supersedes` | new → old | 대체 |
| `refines` | new → old | 정교화 |
| `depends-on` | * → * | 의존 |

> **사후 엣지가 정상이다.** `followed-by`(AR→UD), `resolved-by`(IN→TS), `released-in`/`verified-in`/`invalidated-by`(*→RN) 는 target 이 나중에 생기므로 entry 작성 시점에 달 수 없다. `wm_node.py relate <source> <type> <target>` 로 사후 확정한다. 이때 기존 줄을 갱신하는데, append-only 는 *일어난 일(entry)을 지우거나 고쳐 쓰지 않는다*는 뜻이고 `relations` 는 그 entry 의 현재 그래프 상태라서다. (중복 entry 를 append 하는 방식은 reader 의 first-seen-wins dedup 이 옛 줄을 돌려주므로 애초에 동작하지 않는다.)

## 기록 판단 넛지 (work-memory-check.sh)

`auditlog` 는 PostToolUse 자동 로깅이고 `worklog` 는 workflow TTL 의 `node -> node` 실행 레일을 따라 수행한 작업을 수동으로 남기는 엔트리다. `worklog` 는 세션 종료 요약이나 auditlog 요약이 아니며, workflow node 를 명시할 수 있을 때만 작성한다. workflow 레일이 없거나 벗어난 작업은 undefined 케이스로 보고, 먼저 AD(왜 레일 밖 판단을 했는지) 또는 IN/TS(문제와 해결)를 남긴 뒤 workflow TTL 갱신 후보로 환류한다.

`track-record/insight-record entry 를 언제 남길지`에 대한 판단 트리거는 별도다. `hooks/work-memory-check.sh` 가 비차단 넛지를 띄운다.

> **전달 의미론이 핵심이다.** Provider별 훅 stdout 의미론이 다르므로 `work-memory-check.sh`는 컨텍스트 도달이 확인된 `SessionStart(compact/resume)` 에서만 plain stdout 으로 넛지를 전달한다. `Stop`·`PreCompact`·`SessionEnd` 에서는 출력이 사용자에게 잡음처럼 보이거나 모델에 도달하지 않을 수 있으므로 check hook을 등록하지 않는다.
>
> **`Stop`·`PreCompact` 는 `commit-work-memory.sh` 로 work-memory 변경분을 커밋한다.** 훅 안에서 커밋하면 PostToolUse(auditlog) 를 재트리거하지 않아 auditlog append 무한루프를 피한다. Stop hook 은 `worklog` 를 생성하지 않는다. `worklog` 작성 여부를 판단하는 행위는 에이전트의 AD 성격이며, workflow TTL node 실행 맥락이 있을 때만 별도 CLI로 남긴다.
>
> **v0.6.3 Stop reminder throttle.** Claude Stop 안내처럼 사용자에게 보이는 reminder는 `stop-check.sh` 로 상태 파일을 두고 1회 출력 뒤 다음 Stop 1회를 억제한다. 상태 파일은 `.claude/state/stop-check.state` 이며 `.gitignore` 대상이다. 이 억제는 reminder 출력에만 적용하고, `commit-work-memory.sh` 백스톱은 그대로 실행한다.
>
> **Cloud runtime 주의.** Codex cloud 같은 ephemeral 환경에서는 setup script와 agent phase가 분리되고, project hook 실행·로컬 커밋 side effect가 다음 작업 기억으로 보장되지 않을 수 있다. cloud hand-off는 최종 답변/diff/커밋 가능한 tracked file에 남는 기록을 기준으로 하며, hook은 보조 수단으로만 본다.

1. **track 넛지** *(SessionStart)* — "결정 가치 있는" 변경(`WM_WORTHY_PATHS`, 기본=오케스트레이션 레이어)이 work-memory 최신 기록보다 앞서고 기록 대기가 없으면 → UD/AD/IN/TS 작성 권유.
2. **IN/TS 넛지** *(SessionStart)* — fix/revert 성격의 커밋(WM 최신 기록 이후)이 있는데 IN/TS 기록 대기가 없으면 → IN+TS 회고 공동 기록 권유. track 넛지(WORTHY_PATHS)와 **독립** — 버그는 오케스트레이션 경로 밖 평범한 소스에서도 나므로 fix 커밋 단독으로 판단한다.
3. **insight 넛지** *(SessionStart)* — 종결된 TS 이후 EP 회고가 없으면 → episode 회고 권유 (EP→PT→PR 추상화 유도).
4. **세션 회고 넛지** *(SessionStart 전용)* — 미커밋 소스 변경(WM 밖)이 남아 있고 IN/TS 기록 대기가 없으면 → "직전 세션 통틀어 IN/TS 점검" 권유. 미커밋 작업의 의도(버그/기능)는 git 으로 알 수 없어 Stop(매 턴)에 두면 나그가 되므로, 컴팩트/재개 직후의 회고 시점에만 띄운다.

판단 *기준* 텍스트는 [assets/work-memory-judgment.md](assets/work-memory-judgment.md) 를 프로젝트의 상시 로드 rules(CLAUDE.md/AGENTS.md)에 드롭인한다 — 핵심 원리 6(always-on 위임)과 일치. *상시 로드 텍스트가 주 레버이고, 이 훅은 도달하는 백스톱이다.* `mso-repository-setup` 의 `init.py --hook` 가 이 훅을 SessionStart(compact/resume)에 자동 등록한다.

## 릴리스 컨텍스트 주입 (hooks/release-context.sh, `SessionStart`)

세션 시작 시 `wm_release.py context` 의 derived view — 현재 릴리스 버전, 더 이상 유효하지 않은 기록(invalidated active), 재유효 후보 — 를 plain stdout 으로 컨텍스트에 주입한다. 에이전트가 "지금 어느 버전 위에서 작업 중이고, 어떤 교훈을 더 이상 믿으면 안 되는지"를 세션 첫 턴부터 안다.

- **matcher**: `startup` + `compact` + `resume` — 릴리스 상태는 세션 최초 시작에 가장 가치가 크므로, 넛지류(compact/resume 전용)와 달리 startup 을 포함한다. 전달 의미론은 동일 근거(SessionStart plain stdout).
- **무잡음 보장**: 프로젝트에 RN entry 가 하나도 없으면 무출력 — RN 미사용 프로젝트에 등록돼 있어도 잡음이 없다.
- **copy-form**: `mso-repository-setup`의 `init.py --hook`이 `release-context.sh`와 `wm_release.py`를 `.claude/scripts/` 또는 `.codex/scripts/`로 함께 복사·등록한다.

## UUG 연동 넛지 (hooks/uug-context-hook.py, `UserPromptSubmit`)

uug-grounding 의 `ug.py dispatch --json` 을 read-only subprocess 로 호출해 매 발화의
`intent_id`/`target_project` 를 읽는다. 게이팅 intent(기본 `work-on-project`)에 걸리고
`target_project`가 현재 레포(`PROJECT_DIR`/`CODEX_PROJECT_DIR`/`CLAUDE_PROJECT_DIR`)와 다르며 그 프로젝트에
`agent-context/` 가 있을 때만 위치를 1줄 넛지한다 — 그 외에는 항상 침묵.

uug-grounding SKILL.md 의 "MSO는 UUG를 모른다(단방향)" 원칙에 대한 의도적 예외이며
(user-decision 승인, 2026-07-03). uug-grounding 이 이 머신에 없으면 `mso-repository-setup`
의 `init.py --hook` 이 이 훅의 복사·등록 자체를 생략한다(설치 시점 게이팅) — 훅 내부의
런타임 no-op degrade(`ug.py` 부재/오류/timeout 시 침묵, `work-memory-check.sh` 와 동일
원칙)는 그 위의 이중 안전장치다. `UserPromptSubmit` stdout 전달 경로를 사용하는
Claude/Codex provider에 공통 등록한다.
게이팅 intent 는 `MSO_UUG_CONTEXT_INTENTS`, 비활성화는 `MSO_UUG_CONTEXT_DISABLED=1`.

## Antigravity 어댑터 (hooks/adapter_antigravity.py)

위 훅들은 모두 Claude Code/Codex 식 snake_case stdin·plain stdout 계약으로 작성돼
있다. Antigravity 는 camelCase I/O 에 `PreToolUse`/`PostToolUse`/`PreInvocation`/
`PostInvocation`/`Stop` 5개 이벤트만 제공하고 `SessionStart`/`UserPromptSubmit`/
`PreCompact` 대응 이벤트가 없다(antigravity.google/docs/hooks/, 확인: 2026-08-28).
`adapter_antigravity.py`가 각 훅을 그대로 재사용할 수 있게 이 간극을 흡수한다 —
Antigravity JSON을 legacy 입력으로 변환해 훅을 서브프로세스로 실행하고, 그 stdout을
Antigravity가 기대하는 출력 스키마로 되감는다(PostToolUse → `{}`, Stop →
`{"decision": "continue", "reason": ...}`, PreInvocation → `{"injectSteps":
[{"ephemeralMessage": ...}]}`). 4가지 모드:

| 모드 | 실행 시점 | 근사 대상 | 대상 훅 |
|---|---|---|---|
| `posttooluse` | `PostToolUse` | (그대로) | auditlog.py, scaffold-check.sh |
| `stop` | `Stop` | (그대로) | stop-check.sh, commit-work-memory.sh |
| `session` | `PreInvocation`, `invocationNum==0`에서만 | `SessionStart` | work-memory-check.sh, release-context.sh |
| `turn` | `PreInvocation`, 매 호출 | `UserPromptSubmit` | workflow-context-hook.py, uug-context-hook.py |

`turn` 모드는 uug-context-hook.py 가 읽는 사용자 발화 원문을 `transcriptPath` 의
마지막 user 턴에서 근사한다(Antigravity `PreInvocation` 입력에는 프롬프트 원문
필드가 없음). `stop-check.sh` 처럼 터미널 렌더링을 가정해 ANSI 색상 코드를 찍는
훅은 어댑터가 제거한다. **미검증 가정** — 어댑터·대상 스크립트를 상대경로로
호출하므로 hook 프로세스의 cwd 가 workspace root 라고 가정한다; 등록은
`mso-repository-setup`의 `init.py --hook --provider antigravity` 가 담당한다(copy-form).

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
| **mso-workflow-design** | workflow 의 decision/validation/eval 노드 변경 시 UD/AD entry 자동 생성 권장. 반복 IN/TS/EP/PT는 workflow TTL ABox 업데이트 후보 evidence로 사용한다. |
| **mso-graph-observability** | work-memory JSONL runtime analysis와 별도로 TTL projection을 graph 관측 입력으로 확장 가능. artifact-stream graph 누락은 Markdown 직접 수정이 아니라 workflow TTL edge 보강으로 환류한다. |
| **mso-workflow-optimizer** | work-memory 를 읽기 전용으로 분석해 승격 후보·개선안·낡은 결정·품질 제안 리포트를 만든다. 제안을 채택해 entry 를 만드는 일은 이 스킬의 절차(`wm_node.py`)로 사용자 승인 뒤 한다. |
| **simple-knowledge-zvec** | 본 스킬의 zvec 인덱싱 기반 라이브러리. |

## 의존성

```
pyyaml>=6.0
rdflib>=7.0
pyshacl>=0.31
# zvec 검색 사용 시
zvec  (simple-knowledge-zvec 스킬 통해)
```

## 참고 자료

- [references/schema.yaml](references/schema.yaml) — 공통 jsonl 스키마
- [references/tbox/work-memory-tbox.ttl](references/tbox/work-memory-tbox.ttl) — work-memory graph TBox
- [references/shapes/work-memory-shapes.ttl](references/shapes/work-memory-shapes.ttl) — relation/lifecycle SHACL gate
- [references/cli.md](references/cli.md) — wm_node.py 상세 사용법
- [references/lifecycle.md](references/lifecycle.md) — track → insight 흐름 가이드
- [scripts/wm_node.py](scripts/wm_node.py) — CLI 도구
- [scripts/wm_context.py](scripts/wm_context.py) — 런타임 context-pack 검색 (lexical; 스코어링 정본)
- [scripts/wm_release.py](scripts/wm_release.py) — release derived view (current/validity/context)
- [scripts/wm_to_ttl.py](scripts/wm_to_ttl.py) — JSONL → TTL projection + SHACL validation
- [references/queries/](references/queries/) — release view SPARQL (current/invalidated/revalidation)
- [assets/templates/](assets/templates/) — 타입별 entry 템플릿
