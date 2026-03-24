# Getting Started — mso-model-optimizer v0.1.0

---

## 사전 조건

이 스킬은 다음 MSO Pack 스킬과 연동된다:

| 스킬 | 역할 | 필수 여부 |
|------|------|----------|
| mso-workflow-optimizer | Tier Escalation 트리거, llm-as-a-judge | 트리거 소스 (또는 직접 트리거) |
| mso-agent-audit-log | 평가 결과 기록 | 권장 |
| mso-observability | drift 감지 + 재학습 트리거 | 운영 단계에서 필요 |

---

## 트리거 방법

### 방법 1: Tier Escalation (workflow-optimizer 연동)

`mso-workflow-optimizer`가 Automation Level Lv30→Lv20 전환을 결정하면 자동 트리거.

### 방법 2: 직접 트리거

```
"sop-intent-classifier 도구의 LLM 분류를 경량 모델로 대체해줘"
```

필수 입력:
- `tool_name`: 대상 Smart Tool 이름
- `inference_pattern`: `classification | ner | ranking | tagging | extraction`

---

## 시나리오별 실행 가이드

### 시나리오 A: 라벨 0개 — "데이터는 있는데 라벨이 없다"

```
예상 흐름:
Phase 1   → 비라벨 데이터 5,000건 수집
Phase 1.5 → LS-0: Zero-shot NLI로 초기 분류 → HITL 검증 (클러스터당 3~5개)
            → 검증된 라벨 8+/class 확보 시 LS-1 전환
            → Augmentation으로 증폭
Phase 2   → effective_count ~150 → TL-20 경로 A (SetFit)
Phase 3   → SetFit 학습 (분 단위)
Phase 4   → kNN baseline 대비 성능 향상 확인
```

**소요 시간**: HITL 검증 제외 ~ 30분
**필요 리소스**: CPU 가능 (SetFit)

### 시나리오 B: 소량 라벨 — "클래스당 20~30개 정도 있다"

```
예상 흐름:
Phase 1   → 라벨 데이터 100건 + 비라벨 3,000건 수집
Phase 1.5 → LS-1: Cleanlab 감사 → Back-Translation 3배 증강
Phase 2   → effective_count ~310 → TL-20 경로 B (LoRA)
Phase 3   → LoRA(r=16) 파인튜닝
Phase 4   → LLM baseline 대비 90%+ 성능 확인
```

**소요 시간**: ~1~2시간 (GPU 기준)
**필요 리소스**: RTX 4090 또는 동급 GPU

### 시나리오 C: 중간 라벨 — "1,000건 정도 라벨링했다"

```
예상 흐름:
Phase 1   → 라벨 1,000건 + 비라벨 10,000건
Phase 1.5 → LS-2: Active Learning 3라운드 (+60건) → Augmentation
Phase 2   → effective_count ~3,500 → TL-20 경로 C (표준 FT)
Phase 3   → distilbert 표준 파인튜닝 (epochs 3~5)
Phase 4   → f1 ≥ 0.85 (LLM 대비) 확인
```

**소요 시간**: ~2~4시간
**필요 리소스**: V100+ GPU

### 시나리오 D: 충분한 라벨 — "대규모 라벨 데이터 보유"

```
예상 흐름:
Phase 1   → 라벨 50,000건
Phase 1.5 → LS-3: Phase 2 직행
Phase 2   → effective_count 50K → TL-30
Phase 3   → DAPT → Fine-tune → Distill (선택)
Phase 4   → 고성능 모델 + 소형화 확인
```

**소요 시간**: ~4~12시간
**필요 리소스**: V100+ GPU (Distill 시 추가)

---

## 평가 기준

Phase 4에서 다음 기준을 모두 충족해야 Phase 5(배포)로 진행:

| 지표 | 기준 | 비고 |
|------|------|------|
| f1 | LLM baseline 대비 ≥ 0.85 | 태스크 유형별 가중 |
| latency_ms | LLM 대비 ≤ 20% | 1건 기준 |
| model_size_mb | ≤ 500MB | Smart Tool 내 탑재 |

미달 시:
- `escalation_needed: false` → Phase 2로 회귀 (TL 재판단)
- `escalation_needed: true` → HITL 에스컬레이션

---

## 주요 결정 포인트 (HITL)

| 시점 | 결정 내용 |
|------|----------|
| LS-0 Step 4 | 클러스터 대표 샘플 라벨 확인/수정 |
| LS-1 Step 4 | 추가 라벨링 예산 투입 여부 |
| LS-2 매 라운드 | Active Learning 선정 샘플 라벨링 |
| Phase 4 | 평가 결과 검토 + 배포 적합성 확인 |
| Phase 5 | deploy_spec 최종 승인 |

---

## 상세 참조

| 목적 | 파일 |
|------|------|
| 전체 Phase 상세 | [SKILL.md](../SKILL.md) |
| 불변 규칙 | [core.md](../core.md) |
| Label Strategy 상세 | [modules/module.label-strategy.md](../modules/module.label-strategy.md) |
| Augmentation 상세 | [modules/module.data-augmentation.md](../modules/module.data-augmentation.md) |
| model-decision 상세 | [modules/module.model-decision.md](../modules/module.model-decision.md) |
| Training Level 상세 | [modules/module.training-level.md](../modules/module.training-level.md) |
| 아키텍처 개요 | [architecture.md](architecture.md) |
