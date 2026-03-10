# mso-workflow-optimizer

> 워크플로우 성과를 평가하고 Automation Level을 결정하여 최적화 리포트와 goal을 생성하는 스킬.

---

## 버전 이력

| 버전 | 주요 변경 |
|------|----------|
| v0.0.1 | 초기 설계. 5-Phase 순차 실행 (단일 세션) |
| v0.0.2–0.0.4 | Automation Level 10/20/30 체계 확립, llm-as-a-judge 통합, process-optimizing 모듈 추가 |
| v0.0.5–0.0.6 | audit_global.db 연동, HITL 피드백 루프 안정화, LLM API ENV 규약 정립 |
| **v0.0.7** | **Agent Teams 아키텍처 도입. Proactive Async + Jewels 패턴 설계.** |

### v0.0.7 주요 내용

Agent Teams 기반 Proactive Async + Jewels 패턴을 설계 문서로 확정.

```
optimizer-lead (delegate mode)
    ├── jewel-producer   [background] — audit_global.db 상시 모니터링 + Jewel 생성
    ├── decision-agent   [on-demand]  — 3-Signal + Jewels → Automation Level 결정
    ├── level-executor   [on-demand]  — Level 10/20/30 실행 + audit 기록
    └── hitl-coordinator [on-demand]  — HITL 피드백 + goal.json 생성
```

- `jewel-producer`: haiku 모델, background, `dontAsk`, TeammateIdle hook(`exit 2`)으로 지속 실행
- Jewel 타입 4종: `kpi_drift` / `level_escalation` / `pattern_alert` / `sampling_adjust`
- Signal C에 Jewels 반영. 총 기여 `clip(-10, +10)` 캡으로 과잉 에스컬레이션 방지
- Phase 4 audit logging → `level-executor` 담당 (delegate lead 대신)
- 상세: [`modules/module.agent-team.md`](modules/module.agent-team.md)

---

## v0.1.0 로드맵

### 핵심 기조: Processing Tier 최적화 환경

> 모든 워크플로우는 처음에 Agentic으로 시작한다.
> 패턴이 쌓일수록 Light Model로, 그리고 Logical로 내려간다.
> v0.1.0은 이 하강을 자동으로 감지하고 환경을 설정하는 시스템이다.

```
Agentic processing    ← 패턴 미확립. LLM 전체 판단 필요. 비용 높음.
        ↓ (최적화 방향)
Light Model processing ← 패턴 부분 확립. 경량 모델 + 최소 프롬프트.
        ↓
Logical processing    ← 패턴 완전 확립. 규칙·스크립트만으로 처리. LLM 불필요.
```

**기존 Automation Level과의 매핑:**

| Processing Tier | Automation Level | 의미 |
|----------------|-----------------|------|
| Agentic | Level 30 | 아직 최적화 안 됨. 전체 LLM 평가 필요 |
| Light Model | Level 20 | 부분 최적화. 스크립트 + 경량 LLM |
| Logical | Level 10 | 완전 최적화. 결정론적 규칙만으로 충분 |

**Level 30이 높다고 좋은 것이 아니다.** 목표는 Level 30 → 10으로의 이동이다.

---

### 구성 요소

#### 1. Tier 전환 감지 (jewel-producer 확장)

jewel-producer가 생성하는 jewel에 `tier_downgrade` 타입 추가.
패턴이 충분히 확립됐다고 판단되면 다운그레이드를 권고한다.

| 감지 조건 | 권고 전환 |
|----------|---------|
| Level 30 실행 후 KPI 안정 3회 연속 | Agentic → Light Model |
| Level 20 분석 결과가 동일 패턴 반복 4회 | Light Model → Logical |
| evaluation.py 없이도 rule 기반 판정 가능 | Logical 환경 구축 권고 |

```json
// 신규 jewel type
{
  "type": "tier_downgrade",
  "from_tier": "agentic",
  "to_tier": "light_model",
  "evidence": "KPI 안정 3회 연속 (precision 91-93%)",
  "severity": "medium"
}
```

#### 2. Logical processing 환경 구축

Logical tier로 전환 가능한 워크플로우에 대해 실행 환경을 세팅한다.

- **rule 파일 생성**: `docs/rules/{workflow_name}.rule.yaml` — 결정론적 판정 기준
- **판정 스크립트 생성**: `scripts/logical/{workflow_name}_judge.py` — LLM 없이 실행
- **Level 10 실행 시 rule 우선 체크**: rule 파일 존재 시 reporting을 LLM 없이 처리

```
Logical tier 실행 흐름:
    rule.yaml 로드 → judge.py 실행 → 조건 충족 여부 판정 → report.md 생성
    (LLM 호출 없음)
```

#### 3. Light Model 환경 구축

Light Model tier에서 사용할 경량 프롬프트 템플릿을 관리한다.

- **모델**: haiku (기본), sonnet (복잡한 패턴 분석 시)
- **프롬프트 템플릿**: `configs/light_prompts/{workflow_name}.prompt.md`
  - 컨텍스트 최소화, 구조화된 출력 강제
  - 토큰 예산 명시 (`max_tokens` 상한 설정)

#### 4. Tier 메트릭 추적

`audit_global.db`에 Processing Tier 이력을 기록하고 최적화 KPI를 산출한다.

| 메트릭 | 설명 |
|--------|------|
| `tier_distribution` | 워크플로우별 Agentic/Light/Logical 비율 |
| `downgrade_count` | Tier 하강 횟수 (최적화 진행 지표) |
| `logical_coverage` | Logical로 처리된 워크플로우 수 / 전체 |

**최적화 성공 기준**: `logical_coverage` 증가 추세 + 비용(토큰) 감소.

#### 5. decision-agent 역할 확장

단일 실행의 Level 판단을 넘어, 워크플로우의 **기본 Tier 조정** 여부도 결정한다.

```
기존: "이번 실행은 Level 20"
v0.1.0: "이번 실행은 Level 20" +
         "이 워크플로우의 default tier를 Agentic → Light로 낮춰야 하는가?"
```

`goal.json`에 `tier_recommendation` 필드 추가:
```json
{
  "next_automation_level": 20,
  "tier_recommendation": {
    "current": "agentic",
    "recommended": "light_model",
    "confidence": 0.82,
    "basis": "KPI 안정 3회 + tier_downgrade jewel 2건"
  }
}
```

#### 6. jewel-producer 서브에이전트 정식 등록

현재 module.agent-team.md 텍스트 정의만 존재. 실제 실행을 위해 등록 필요.

```
.claude/agents/mso-jewel-producer.md  ← 신규
```

`tier_downgrade` jewel 생성 로직 포함.

---

## 파일 구조

```
mso-workflow-optimizer/
├── README.md                          # 이 파일
├── SKILL.md                           # 스킬 진입점 (v0.0.7)
├── DIRECTORY.md                       # 디렉토리 명세
├── core.md                            # 용어·인터페이스·규칙
├── modules/
│   ├── modules_index.md
│   ├── module.agent-team.md           # v0.0.7 신규: Agent Teams 아키텍처
│   ├── module.agent-decision.md       # v0.0.7 수정: Signal C + Jewels
│   ├── module.analysis-optimizing.md
│   ├── module.automation-level.md
│   ├── module.hitl-feedback.md
│   ├── module.process-optimizing.md
│   └── module.llm-as-a-judge.md
├── scripts/
│   └── select_llm_model.py
├── configs/
│   └── llm-model-catalog.yaml
└── schemas/
    └── optimizer_result.schema.json
```
