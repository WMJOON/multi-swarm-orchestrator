---
name: mso-work-memory
version: "0.6.4"
description: >
  프로젝트의 작업 기록을 jsonl + 임베딩 + 그래프 형태로 자산화하는 스킬.
  agent-context/work-memory/ 에 7종 entry (issue-note, agent-decision,
  user-decision, trouble-shooting, episode, pattern, principle) + auditlog/worklog
  를 jsonl 로 보관. zvec 시맨틱 검색 + relations 그래프 traversal +
  TTL projection/SHACL validation 지원.
  다음 상황에서 사용한다:
  (1) 새 이슈·결정·사고·회고 entry 추가,
  (2) 과거 사례 시맨틱 검색 ("비슷한 timeout 사고 있었나?"),
  (3) 그래프 traversal ("이 decision 이 어떤 사고로 이어졌나"),
  (4) 정기 회고 (episode → pattern → principle 추출),
  (5) 자동 hook (session 이벤트 → auditlog jsonl append).
---

# MSO Work Memory

프로젝트의 운영 기록과 인사이트를 jsonl 파일 + zvec 임베딩 + 그래프 relations 로 자산화한다. 단기 운영 흐름 (track-record) 과 장기 자산화 (insight-record) 를 분리한다. JSONL은 append-only SSOT이고, TTL은 관계/라이프사이클 검증을 위한 projection layer다.

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
└── insight-record/             # ── 추상화 그래디언트 (타입별 aggregate) ──
    ├── episode.jsonl             (EP-NNNN …)
    ├── pattern.jsonl             (PT-NNNN …)
    └── principle.jsonl           (PR-NNNN …)
```

> **마이그레이션**: 구버전(v1.1.x)은 `track-record/<type>/<ID>.jsonl` per-entry 파일이었다.
> `scripts/wm_migrate.py`(dry-run 기본, `--apply`)로 타입별 aggregate 로 합치고 원본은
> `.migration-archive/` 로 옮긴다. reader(validate/show/graph/stats/ttl)는 신/구를 모두
> 읽지만 **같은 트리 안 공존은 DUP-ID 를 유발**하므로 마이그레이션 후 archive 가 필수다.

## Entry 타입 매트릭스

| Prefix | Type | 영역 | 작성 시점 |
|---|---|---|---|
| **IN** | issue-note | track | 문제 발견 즉시 |
| **AD** | agent-decision | track | 에이전트가 **결정 권한 내에서** 판단 내리고 즉시 실행할 때 |
| **AR** | alternatives-record | track | 에이전트/사용자가 **상위 권위(oracle)에 옵션을 올릴 때** (결정 전, 옵션+득실) |
| **UD** | user-decision | track | 사용자가 정책·구조 결정 시 (structural 태그 → ADR / boundary → drift 추적) |
| **TS** | trouble-shooting | track | 해결 종결 시 (resolution + prevention) |
| **EP** | episode | insight | 사건이 일단락된 후 회고 (TS 다음) |
| **PT** | pattern | insight | EP 여러 개 누적 후 반복 발견 |
| **PR** | principle | insight | PT 안정화 후 응축된 원칙 |
| AU | auditlog | (자동) | hook이 append |
| WL | worklog | (수동) | workflow TTL node 실행 결과 기록 시 |

## 라이프사이클 그래프

```
IN ──raised──> AD                    (agent 권한 내 결정·실행)
IN ──raised──> AR ──followed-by──> UD (oracle 에게 옵션 제시 → 결정)
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

상세 스키마: [references/schema.yaml](references/schema.yaml).

## 의사결정 거버넌스 컨벤션 (v0.5.0)

척추 원리 — **Deliberation is a View**: 코어는 이벤트(IN/AR/AD/UD)와 관계만 저장한다. "의사결정 케이스"·"drift 사건"은 별도 노드로 저장하지 않고 그래프에서 **쿼리로 재구성되는 view** 다.

- **AD vs AR 구분** — *agent 가 결정 권한을 갖고 즉시 실행* → **AD**. *agent 가 상위 권위(oracle = user 또는 metric/KPI)에 옵션을 올림* → **AR**. AR 은 결정하지 않으며, 채택 시 `followed-by` 로 UD 에 연결한다. (프로젝트가 oracle-strict 면 AD 비활성화는 schema 선택사항.)
- **oracle ∈ {human, metric}** — 결정 권위는 사람만이 아니다. eval 대조가 지표 기반이면 metric/KPI 게이트도 oracle 이다.
- **DriftEvent = derived** — drift 는 노드가 아니라, 같은 `UD.boundary` 의 시간순 체인에 형성되는 `supersedes`/`refines` 링크다. 그 링크 자체가 drift event.
- **DecisionCase = view → episode** — 진행 중 케이스는 IN 을 root 로 한 traversal subgraph(view)다. 종결 시 회고로 결정화하면 기존 `episode`(EP) 가 그 envelope — 신규 타입을 만들지 않는다.
- **policy → stale 캐스케이드** — 코어는 "UD.boundary + supersedes=drift event" 신호까지만 책임진다. drift→stale 재처리 큐의 *구현*은 산출물 모델에 의존하므로 프로젝트 영역(레퍼런스 패턴).

> **타입 어휘는 schema-driven (v0.3.4+).** `wm_node.py` 는 타입 prefix/dir 과 relation 어휘를 `WORKMEM_DIR/schema.yaml` 의 `types:`/`relation_types:` 에서 읽는다(없으면 기본 7타입 fallback — 하위호환). 같은 엔진을 다른 스코프(예: user-memory UC/UP/UF)로 재사용하려면 그 스코프의 `schema.yaml` 에 `types:` 만 다르게 둔다.

## CLI: `wm_node.py`

```bash
# 새 entry 작성 (대화형 stub 출력)
python wm_node.py new <type> --title "..." [--tags a,b,c] [--related TS-0017:resolved-by]

# 검증 (단일 파일 또는 디렉토리 전체)
python wm_node.py validate <path>

# TTL projection 생성 + SHACL 검증
python wm_to_ttl.py project agent-context/work-memory
python wm_to_ttl.py validate agent-context/work-memory --ttl-out agent-context/work-memory/graph/work-memory.abox.ttl

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
- [scripts/wm_to_ttl.py](scripts/wm_to_ttl.py) — JSONL → TTL projection + SHACL validation
- [assets/templates/](assets/templates/) — 타입별 entry 템플릿
