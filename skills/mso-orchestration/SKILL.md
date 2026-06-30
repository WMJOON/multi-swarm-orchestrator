---
name: mso-orchestration
version: "0.5.1"
description: "MSO 스킬 팩 라우터. v0.5.0: workflow/artifact/eval graph 역할을 분리하고, §11 NLU 재편에 따라 utterance→intent 는 UUG, MSO 는 intent→action 및 MSO runtime 신호만 담당한다. MSO는 workflow/work-memory의 소유자이며 MSM(가칭)의 ontology KB를 소비한다."
triggers:
  - "mso 시작"
  - "MSO init"
  - "agent-context 부트스트랩"
  - "스캐폴드 설계"
  - "워크플로우 설계"
  - "work-memory"
  - "audit-log"
  - "work-log"
  - "track-record"
  - "insight-record"
  - "decision 기록"
  - "episode 작성"
  - "pattern 추출"
  - "principle 응축"
  - "harness manifest"
  - "workflow optimizer"
  - "graph observability"
  - "그래프 관측"
  - "mso graph"
  - "workflow observability"
  - "워크플로우 관측"
  - "workflow 시각화"
  - "work-memory 분석"
  - "auditlog 분석"
  - "이상행동 관측"
  - "실패 흐름 분석"
  - "Mermaid view"
  - "TTL graph"
  - "LangGraph"
  - "langgraph 변환"
  - "workflow TTL 실행"
  - "utterance grounding"
  - "운영 명령"
  - "ticket 재실행"
  - "방금 fail한"
  - "conversation analytics"
  - "전환 분석"
  - "reprompt 분석"
---

# MSO Orchestration (v0.5.0)

MSO 스킬 팩의 **단일 진입점**. 사용자 의도를 트리거 매칭해 적절한 sub-skill 로 안내한다.

본 스킬은 **로직을 갖지 않는다** — 흐름 정의·라우팅만. 도메인 동작은 모두 sub-skill 위임.

## Boundary Update

- **MSO**: repository workflow, task rail, slot spec, dispatch, work-memory/decision memory를 소유한다.
- **MSM(가칭)**: ontology knowledge base를 제공하고 AI의 추론 경로를 제약하는 구조 지식을 만든다. MSO workflow는 필요 시 이 ontology를 소비한다.
- **UUG**: MSO/MSM 사용 편의 레이어다. 반복 이벤트와 사용자 선호를 바탕으로 entity-filling proposal을 만들 수 있지만, MSO workflow의 slot spec이나 MSM ontology 정본을 직접 수정하지 않는다.
- User decision drift와 bias correction은 work-memory/UUG preference projection의 관측 신호로 남기고, workflow/ontology 정본 변경은 각 소유 레이어의 HITL/decision 절차를 거친다.

## Flow (전체 라이프사이클)

```
[init]                                                                   
  mso-repository-setup        ←── 표준 구조 부트스트랩 (agent-context/)  
        │                                                                
        ▼                                                                
[설계]                                                                   
  mso-scaffold-design         ←── index.yaml SSOT (모듈·subdir·sub_index) 
  mso-workflow-design         ←── workflow/artifact/eval TTL ABox node-edge shape
  mso-graph-observability     ←── TTL view + artifact stream 개선 리포트 + runtime graph 관측
  mso-workflow-optimizer      ←── workflow TTL → LangGraph generated artifact
        ↕ 협업 (multi-turn discussion, v1.0.0+ 예정)                       
  mso-discussion-coworker     ←── 옵션 비교·결정 근거 추적·UD/AD 자동 작성
        │                                                                
        ▼                                                                
[운영 — 자연어 명령 레이어 (§11 재편)]                                  
  ┌─────────────────────────────────────────────────────┐               
  │  앞단(utterance→intent) = UUG (uug-grounding, repo 밖)             │
  │    └ `ug ground "<발화>"` → intent_id (+target_project)            │
  │              │  intent_id                            │               
  │              ▼                                       │               
  │  mso-intent-analytics  ←── 뒷단 dispatch + registry SoT            │
  │    ├── lookup (Intent/SlotSpec/IntentMatrix 조회)   │               
  │    └── pipeline.ground(utterance, intent_id):       │               
  │         slot_filler → resolver → SHACL validator → turn_writer     │
  │              │                                      │               
  │              ▼  GroundedCommand                     │               
  │  mso-orchestration: intent_id → Smart Tool 디스패치 │               
  └─────────────────────────────────────────────────────┘               
        │                                                                
        ▼                                                                
[실행 — harness: logging]                                                
  → agent-context/work-memory/auditlog/   (자동 hook)                    
  → workspace/.mso-context/conversation/turns.jsonl  (IntentTurn 기록)   
  → agent-context/work-memory/worklog/    (일별)                         
        │                                                                
        ▼                                                                
[분석 — Conversation Analytics] ⚠ de-routed (§11.1)                      
  mso-conversation-analytics (잔존, 라우팅 제외 — 직접 호출만)          
    └ 분석 메서드 → UUG(uug-pattern-analytics) 흡수 대상,               
      MSO runtime tier-escalation 신호 → mso-intent-analytics 귀속     
        │                                                                
        ▼                                                                
[운영 — decision 기록]                                                  
  mso-work-memory                                                        
    ├── track-record/                                                    
    │   ├── issue-note      (IN-NNNN)                                    
    │   ├── agent-decision  (AD-NNNN)                                    
    │   ├── user-decision   (UD-NNNN, structural 태그 = repository-ADR)  
    │   └── trouble-shooting (TS-NNNN)                                   
    │                                                                    
    └── insight-record/    ←── trigger: 회고 시점                        
        ├── episodes       (EP-NNNN)  ←── TS 다음 회고                   
        ├── patterns       (PT-NNNN)  ←── EP 누적 패턴                   
        └── principles     (PR-NNNN)  ←── PT 응축 원칙                   
        │                                                                
        ▼                                                                
[실행 최적화 — generated graph]
  mso-workflow-optimizer
    ├── workflow TTL ABox → LangGraph artifact
    └── provider policy(cost/speed/quality/privacy) → node routing
```

## Sub-skills (name-only)

본 스킬은 다음 sub-skill 들을 트리거하기만 한다. 실제 동작·스키마·CLI 는 각 SKILL.md 참조.

| Skill | 책임 | 주요 트리거 |
|---|---|---|
| **mso-repository-setup** | agent-context/ 부트스트랩 (init/check/migrate). artifact stream TTL이 있으면 scaffold/observability 후속 점검으로 연결 | "mso init", "agent-context 부트스트랩", "워크플로우 디렉토리 생성" |
| **mso-scaffold-design** | index.yaml SSOT, 계층 sub_index, data_registry. artifact stream TTL 경로를 index/sub-module에 연결 | "스캐폴드 설계", "index.yaml", "모듈 추가", "디렉토리 등록", "artifact registry" |
| **mso-workflow-design** | workflow/artifact/eval TTL ABox node-edge 생성 및 shape 점검. legacy YAML은 import input | "워크플로우 설계", "workflow TTL", "artifact stream", "eval 노드", "decision 노드", "validation 노드" |
| **mso-graph-observability** | TTL 가시화와 개선 리포트 생성. workflow view, artifact-stream view, eval edge, runtime analysis를 읽기 전용 산출물로 생성 | "그래프 관측", "워크플로우 관측", "artifact stream report", "work-memory 분석", "auditlog 분석", "이상행동 관측", "실패 흐름 분석" |
| **mso-workflow-optimizer** | workflow TTL ABox를 LangGraph generated artifact로 컴파일. TTL은 SSOT로 유지하고 provider routing은 정책 파일로 분리 | "workflow optimizer", "LangGraph", "langgraph 변환", "workflow TTL 실행", "Ollama 비용 최적화" |
| **mso-work-memory** | jsonl entry CRUD, zvec 검색, relations 그래프 | "decision 기록", "trouble-shooting 작성", "episode 회고", "비슷한 사고 검색" |
| **mso-intent-analytics** *(§11 재편)* | registry SoT (Intent/SlotSpec/IntentMatrix, RDF+LinkML, Lookup API) **+ 뒷단 dispatch** (`pipeline.ground(utterance, intent_id)`: slot_filler→resolver→SHACL validator→turn_writer→GroundedCommand). 앞단(utterance→intent)은 UUG. MSO runtime tier-escalation 신호의 귀속지 | "ticket-NNN 재실행", "run-NNN 상태", "audit 조회", "dispatch", "intent 목록", "슬롯 스키마" |
| ~~구 utterance-grounding~~ | **해체(§11)**: 앞단(utterance→intent)→UUG(uug-grounding), 뒷단→mso-intent-analytics 흡수. 스킬 제거됨 | — |
| ~~conversation-analytics~~ | **de-route(§11.1)**: 잔존하나 라우팅 제외. 전환행렬·funnel·reprompt율 등 사용자/turn 패턴 메서드는 UUG(`uug-pattern-analytics`) 흡수 대상. 직접 호출만 | — |
| **mso-discussion-coworker** *(v1.0.0+ 예정)* | workflow 설계·정책 결정 시 multi-turn discussion 협업. 사용자 의도 정교화·옵션 비교·결정 근거 기록 (→ work-memory UD/AD 자동 작성) | "워크플로우 같이 만들자", "옵션 비교해줘", "이거 어떻게 할지 논의", "discussion-coworker" |

## 라우팅 규칙

사용자 발화의 의도를 다음 우선순위로 매칭한다.

0. **[§11 재편] 자연어 운영 명령** (예: "ticket-217 재실행", "run-abc 상태 확인", "audit 로그 조회") → UUG `ug ground` 로 intent_id 해석(앞단) → `mso-intent-analytics` `pipeline.ground(utterance, intent_id)` 로 GroundedCommand 조립(뒷단) → intent_id 기반 Smart Tool 디스패치
1. **init·부트스트랩 의도** (예: "프로젝트 처음 셋업", "agent-context 만들어") → `mso-repository-setup`
2. **구조 정의 의도** (예: "모듈 추가", "subdir 등록", "디렉토리 패턴") → `mso-scaffold-design`
3. **흐름 정의 의도** (예: "워크플로우 만들어", "결정 게이트", "검증 단계") → `mso-workflow-design`
4. **graph 관측·분석 의도** (예: "워크플로우 관측", "workflow topology 보여줘", "어떤 흐름에서 실패가 많아?", "agent 이상행동 관측", "work-memory/auditlog 분석") → `mso-graph-observability`
5. **workflow 실행 최적화 의도** (예: "workflow TTL을 LangGraph로 변환", "Ollama 비용 최적화 실행 그래프", "Codex/API provider routing") → `mso-workflow-optimizer`
6. **discussion 의도** (예: "같이 결정하자", "옵션 비교", "이렇게 vs 저렇게") → `mso-discussion-coworker` *(v1.0.0+)*
7. **기록·검색·회고 의도** (예: "이 결정 기록해", "비슷한 사고 검색", "패턴 추출") → `mso-work-memory`
8. **발화·turn 패턴 분석 의도** (예: "전환 행렬 보여줘", "reprompt율 분석", "unresolved 발화") → UUG `uug-pattern-analytics` 우선. MSO `conversation-analytics`는 de-routed 잔존 스킬이므로 자동 라우팅하지 않고 직접 호출만 허용

## Non-Goals

- 도메인 로직 (실제 yaml 작성, jsonl entry 생성, 그래프 traversal) → sub-skill 위임
- hook 자동 등록 → sub-skill `mso-work-memory` 의 hooks/ 사용 가이드 참조
- 다중 프로젝트 관리 → 각 프로젝트가 독립적으로 sub-skill 호출
- Intent 분류(utterance→intent) → UUG(uug-grounding) 위임. intent→action(slot/dispatch)만 `mso-intent-analytics` 위임

## 사용 시나리오

### 새 프로젝트
```
사용자: "이 프로젝트에 MSO 도입해줘"
  → mso-orchestration: mso-repository-setup 안내
  → 사용자가 `init.py --target .` 실행
  → 이어서: mso-scaffold-design 으로 모듈 등록
  → 이어서: mso-workflow-design 으로 워크플로우 정의
```

### 자연어 운영 명령 (§11 재편)
```
사용자: "ticket-217 재실행"
  → 앞단: UUG  ug ground "ticket-217 재실행" → intent_id="dispatch_ticket"
  → 뒷단: mso-intent-analytics  pipeline.ground("ticket-217 재실행", intent_id="dispatch_ticket")
       → GroundedCommand {
            intent_id: "dispatch_ticket",
            target_id: "ticket-217",
            target_concepts: ["TicketEvent","FailedTicket"],
            slots: {"ticket_ref":"ticket-217","reason":"manual_retry"},
            tier: "UUG", reprompt_needed: false
         }
  → dispatch_ticket Smart Tool 실행
  → turns.jsonl append (IntentTurn 기록)
```

### 기존 프로젝트 마이그레이션
```

### Workflow Optimizer
```
사용자: "이 workflow ttl을 LangGraph로 변환해줘"
  → mso-orchestration: mso-workflow-optimizer 안내
  → python scripts/compile_workflow.py agent-context/workflow/workflow-00.abox.ttl \
       --out generated/langgraph --mode cost
```
사용자: "기존 평탄 구조를 agent-context/ 로 옮겨줘"
  → mso-orchestration: mso-repository-setup --migrate 안내
```

### 사고 발생
```
사용자: "방금 그 timeout 누락, 기록 남기자"
  → mso-orchestration: mso-work-memory 안내
  → `wm_node.py new issue-note ...`
  → 해결 후: `wm_node.py new trouble-shooting ...`
  → 회고 시점: `wm_node.py new episode --related TS-NNNN:analyzed-in`
```

### Pattern Analytics 경계 (v0.5.0)
```
사용자: "이번 주 전환 패턴 분석해줘"
  → UUG: uug-pattern-analytics 안내 (사용자/turn 패턴, 자주 쓰는 workflow 후보)
  → MSO: mso-conversation-analytics 는 de-routed legacy capability. 필요할 때만 직접 python src/analytics.py 호출
  → MSO runtime tier-escalation 신호는 mso-intent-analytics 귀속
```

## 참고 자료

- 각 sub-skill 의 SKILL.md (실제 사용법은 거기로)
- [docs/contracts/GroundedCommand.md](../../docs/contracts/GroundedCommand.md) — Grounded Command 계약 (governance)
- [references/routing-rules.md](references/routing-rules.md) — 트리거 매칭 상세 (v0.5.0+ 추가 예정)
