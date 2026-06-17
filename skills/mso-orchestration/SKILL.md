---
name: mso-orchestration
version: "0.3.1"
description: "MSO 스킬 팩 라우터. §11 NLU 재편: utterance→intent 는 UUG(uug-grounding) 위임, MSO 는 intent→action(mso-intent-analytics 뒷단 dispatch). name-only 라우팅."
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
  - "utterance grounding"
  - "운영 명령"
  - "ticket 재실행"
  - "방금 fail한"
  - "conversation analytics"
  - "전환 분석"
  - "reprompt 분석"
---

# MSO Orchestration (v0.3.1)

MSO 스킬 팩의 **단일 진입점**. 사용자 의도를 트리거 매칭해 적절한 sub-skill 로 안내한다.

본 스킬은 **로직을 갖지 않는다** — 흐름 정의·라우팅만. 도메인 동작은 모두 sub-skill 위임.

## Flow (전체 라이프사이클)

```
[init]                                                                   
  mso-repository-setup        ←── 표준 구조 부트스트랩 (agent-context/)  
        │                                                                
        ▼                                                                
[설계]                                                                   
  mso-scaffold-design         ←── index.yaml SSOT (모듈·subdir·sub_index) 
  mso-workflow-design         ←── workflow YAML (step/decision/validation)
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
    └ 분석 메서드 → UUG(uug-pattern-analytics) 흡수 예정,               
      tier-escalation 신호 → mso-intent-analytics 귀속 예정             
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
[최적화 — trigger]                                                       
  optimization layer (v1.0.0+ 예정)                                          
    ├── pattern → workflow 자동 갱신                                     
    └── principle → policy gate 보완                                     
```

## Sub-skills (name-only)

본 스킬은 다음 sub-skill 들을 트리거하기만 한다. 실제 동작·스키마·CLI 는 각 SKILL.md 참조.

| Skill | 책임 | 주요 트리거 |
|---|---|---|
| **mso-repository-setup** | agent-context/ 부트스트랩 (init/check/migrate) | "mso init", "agent-context 부트스트랩", "워크플로우 디렉토리 생성" |
| **mso-scaffold-design** | index.yaml SSOT, 계층 sub_index | "스캐폴드 설계", "index.yaml", "모듈 추가", "디렉토리 등록" |
| **mso-workflow-design** | workflow YAML, 노드 스키마, harness manifest | "워크플로우 설계", "workflow YAML", "judge", "decision 노드", "validation 노드" |
| **mso-work-memory** | jsonl entry CRUD, zvec 검색, relations 그래프 | "decision 기록", "trouble-shooting 작성", "episode 회고", "비슷한 사고 검색" |
| **mso-intent-analytics** *(§11 재편)* | registry SoT (Intent/SlotSpec/IntentMatrix, RDF+LinkML, Lookup API) **+ 뒷단 dispatch** (`pipeline.ground(utterance, intent_id)`: slot_filler→resolver→SHACL validator→turn_writer→GroundedCommand). 앞단(utterance→intent)은 UUG. | "ticket-NNN 재실행", "run-NNN 상태", "audit 조회", "dispatch", "intent 목록", "슬롯 스키마" |
| ~~구 utterance-grounding~~ | **해체(§11)**: 앞단(utterance→intent)→UUG(uug-grounding), 뒷단→mso-intent-analytics 흡수. 스킬 제거됨 | — |
| ~~conversation-analytics~~ | **de-route(§11.1)**: 잔존하나 라우팅 제외. 분석 메서드 UUG 흡수 대기, 직접 호출만 | — |
| **mso-discussion-coworker** *(v1.0.0+ 예정)* | workflow 설계·정책 결정 시 multi-turn discussion 협업. 사용자 의도 정교화·옵션 비교·결정 근거 기록 (→ work-memory UD/AD 자동 작성) | "워크플로우 같이 만들자", "옵션 비교해줘", "이거 어떻게 할지 논의", "discussion-coworker" |

## 라우팅 규칙

사용자 발화의 의도를 다음 우선순위로 매칭한다.

0. **[§11 재편] 자연어 운영 명령** (예: "ticket-217 재실행", "run-abc 상태 확인", "audit 로그 조회") → UUG `ug ground` 로 intent_id 해석(앞단) → `mso-intent-analytics` `pipeline.ground(utterance, intent_id)` 로 GroundedCommand 조립(뒷단) → intent_id 기반 Smart Tool 디스패치
1. **init·부트스트랩 의도** (예: "프로젝트 처음 셋업", "agent-context 만들어") → `mso-repository-setup`
2. **구조 정의 의도** (예: "모듈 추가", "subdir 등록", "디렉토리 패턴") → `mso-scaffold-design`
3. **흐름 정의 의도** (예: "워크플로우 만들어", "결정 게이트", "검증 단계") → `mso-workflow-design`
4. **discussion 의도** (예: "같이 결정하자", "옵션 비교", "이렇게 vs 저렇게") → `mso-discussion-coworker` *(v1.0.0+)*
5. **기록·검색·회고 의도** (예: "이 결정 기록해", "비슷한 사고 검색", "패턴 추출") → `mso-work-memory`
6. **분석·환류 의도** (예: "전환 행렬 보여줘", "reprompt율 분석", "unresolved 발화") → ⚠ de-routed(§11.1). 자동 라우팅 안 함 — `conversation-analytics` 직접 호출(`python src/analytics.py`)만. 분석 메서드 UUG 흡수 후 제거 예정
7. **최적화 의도** (v1.0.0+ 예정)

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

### Conversation Analytics (v0.3.1)
```
사용자: "이번 주 전환 패턴 분석해줘"
  → mso-orchestration: mso-conversation-analytics 안내
  → python src/analytics.py --query transition_matrix --days 7
  → 또는 python src/analytics.py --feedback --days 7
```

## 참고 자료

- 각 sub-skill 의 SKILL.md (실제 사용법은 거기로)
- [docs/contracts/GroundedCommand.md](../../docs/contracts/GroundedCommand.md) — Grounded Command 계약 (governance)
- [references/routing-rules.md](references/routing-rules.md) — 트리거 매칭 상세 (v0.4.0+ 추가 예정)
