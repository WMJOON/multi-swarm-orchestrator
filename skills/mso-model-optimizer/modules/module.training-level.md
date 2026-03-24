# module.training-level

> Phase 3 전용. Training Level TL-10/20/30 각각의 실행 흐름 상세.

---

## TL-10 — Rule/Heuristic 생성

```mermaid
flowchart LR
    data[("clean_dataset")] --> extract{{"rule_engine.py"}} --> rules["rules.json"]
```

### 적합 상황

- 데이터 < 100건 또는 태스크가 결정론적
- regex, 키워드 매칭, 임계값 기반으로 해결 가능
- LLM 호출을 완전히 제거하고 deterministic 처리로 전환

### 실행 단계

1. **패턴 분석**: `clean_dataset.jsonl`에서 input→output 매핑의 결정론적 패턴을 추출한다
   - 동일 입력 → 동일 출력 비율 계산
   - 고빈도 패턴 클러스터링
2. **규칙 생성**: `rule_engine.py` 실행
   - 키워드 기반 규칙 추출
   - 정규표현식 패턴 도출
   - 임계값 기반 분기 조건 생성
3. **규칙 검증**: validation split으로 규칙 커버리지 측정
   - 커버리지 < 80% → warning 기록 + HITL에 수동 규칙 보완 요청
4. **rules.json 저장**: `{workspace}/.mso-context/active/<run_id>/model-optimizer/tl10_model/rules.json`

### rules.json 형식

```json
{
  "version": "1.0",
  "task_type": "classification",
  "rules": [
    {
      "id": "r001",
      "condition": { "type": "keyword", "pattern": "환불|반품|취소", "field": "input" },
      "output": { "label": "refund_request", "confidence": 0.95 },
      "priority": 1
    },
    {
      "id": "r002",
      "condition": { "type": "regex", "pattern": "^[0-9]{10,13}$", "field": "order_id" },
      "output": { "label": "order_lookup", "confidence": 0.99 },
      "priority": 2
    }
  ],
  "fallback": {
    "action": "escalate_to_llm",
    "note": "규칙 미매칭 시 LLM fallback"
  },
  "coverage": 0.87,
  "generated_from": "<dataset_stats hash>"
}
```

### 산출물

| 파일 | 경로 |
|------|------|
| rules.json | `tl10_model/rules.json` |
| coverage_report.md | `tl10_model/coverage_report.md` |
| training_log.jsonl | `tl10_model/training_log.jsonl` |

---

## TL-20 — 경량 모델 파인튜닝

> TL-20은 라벨 수와 태스크 유형에 따라 3가지 학습 경로를 제공한다.
> model-decision의 `base_model` 필드와 `label_strategy_output.json`의 LS 레벨로 자동 라우팅된다.

### 학습 경로 라우팅

```mermaid
flowchart TD
    decision["model-decision 출력"] --> check{"effective_count?"}
    check -->|"50~200</br>labeled >= 8/class"| setfit["경로 A: SetFit"]
    check -->|"200~2K"| lora["경로 B: LoRA/QLoRA"]
    check -->|"2K~10K"| standard["경로 C: 표준 Fine-tuning"]
    setfit --> model["model/"]
    lora --> model
    standard --> model
```

| 경로 | 조건 | 학습 방식 | 특징 |
|------|------|----------|------|
| **A: SetFit** | effective_count 50~200, classification | Contrastive + 경량 분류기 | 클래스당 8개로 GPT-3급 |
| **B: LoRA/QLoRA** | effective_count 200~2K | 저랭크 어댑터 파인튜닝 | Full FT 대비 90~95% 품질, VRAM 10~20배↓ |
| **C: 표준 Fine-tuning** | effective_count 2K~10K | 전체 파라미터 업데이트 | 검증된 기본 방식 |

> 사용자가 경로를 직접 지정할 수 있다. 미지정 시 자동 라우팅.

#### 태스크 유형별 라우팅 오버라이드

effective_count 기반 라우팅은 classification 기본 기준이다. **NER/tagging 태스크**는 per-entity count가 라우팅을 오버라이드한다:

| inference_pattern | 오버라이드 조건 | 라우팅 |
|-------------------|---------------|--------|
| classification | 없음 (effective_count 기준) | 위 표 참조 |
| NER | min(entity별 라벨 수) < 500 | **경로 B (LoRA)** — effective_count 무관 |
| NER | min(entity별 라벨 수) ≥ 500 | effective_count 기준 (경로 C 또는 그 이상) |
| tagging | 위 NER 규칙과 동일 | 동일 |
| ranking | 없음 (항상 임베딩 기반) | 별도 처리 |

> NER은 토큰 레벨 태스크이므로 전체 데이터 수보다 entity 유형당 라벨 수가 학습 품질을 결정한다.

---

### 경로 A: SetFit (Few-shot)

```mermaid
flowchart LR
    data[("labeled_dataset</br>8~50/class")] --> contrastive{{"SetFit contrastive</br>fine-tuning"}} --> head{{"분류 헤드 학습"}} --> model["model/"]
```

#### 적합 상황

- 클래스당 8~50개 라벨
- 텍스트 분류 (binary, multi-class)
- 빠른 프로토타입 또는 라벨 수집 전 조기 배포

#### 실행 단계

1. **Sentence Transformer 로드**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (한국어 포함) 또는 model-decision 지정 모델
2. **Contrastive 학습 데이터 구성**: 라벨 기반 양성/음성 쌍 자동 생성
3. **SetFit 학습 실행**: `setfit_train.py`
   - 기본 하이퍼파라미터:
     - num_iterations: 20
     - num_epochs: 1
     - batch_size: 16
     - learning_rate: 2e-5
4. **분류 헤드 학습**: Logistic Regression (기본) 또는 소형 MLP
5. **모델 저장**: SetFit 모델 + 분류 헤드

#### 산출물

| 파일 | 경로 |
|------|------|
| model/ | `tl20_model/model/` (SetFit 모델) |
| training_log.jsonl | `tl20_model/training_log.jsonl` |
| config.json | `tl20_model/config.json` (`training_route: "setfit"`) |

---

### 경로 B: LoRA/QLoRA (PEFT)

```mermaid
flowchart LR
    base["base_model</br>(frozen)"] --> lora{{"LoRA adapter</br>fine-tuning"}} --> model["model/</br>(base + adapter)"]
    data[("labeled_dataset</br>200~2K")] --> lora
```

#### 적합 상황

- 라벨 200~2K건
- GPU 자원 제약 환경 (QLoRA: 4-bit 양자화로 RTX 4090 1장)
- 대형 base model(7B+) 도메인 적응

#### 실행 단계

1. **base_model 로드**: model-decision에서 결정된 모델
   - 7B 이상 모델 + GPU VRAM < 24GB → QLoRA 자동 전환
2. **LoRA 설정**:
   - 기본 하이퍼파라미터:
     - lora_rank (r): 16
     - lora_alpha: 32
     - lora_dropout: 0.05
     - target_modules: ["q_proj", "v_proj"] (모델 구조에 따라 조정)
   - QLoRA 추가 설정:
     - quantization: 4-bit (nf4)
     - double_quantization: true
3. **파인튜닝 실행**: `lora_finetune.py`
   - learning_rate: 2e-4 (LoRA는 표준 FT보다 높은 lr 사용)
   - epochs: 3~5 (early stopping with patience=2)
   - warmup_ratio: 0.03
   - weight_decay: 0.05
4. **validation 평가**: epoch마다 validation loss + f1 측정
5. **어댑터 저장**: LoRA adapter weights만 별도 저장 (base model은 참조)
6. **어댑터 병합** (선택): 배포 시 `merge_and_unload()`로 단일 모델 생성
7. **ONNX 변환** (선택): 병합 후 변환 가능

#### 산출물

| 파일 | 경로 |
|------|------|
| adapter_model/ | `tl20_model/adapter_model/` (LoRA weights) |
| merged_model/ | `tl20_model/model/` (병합 시, PyTorch 또는 ONNX) |
| tokenizer/ | `tl20_model/tokenizer/` |
| training_log.jsonl | `tl20_model/training_log.jsonl` |
| config.json | `tl20_model/config.json` (`training_route: "lora"` 또는 `"qlora"`) |

---

### 경로 C: 표준 Fine-tuning

```mermaid
flowchart LR
    base["base_model"] --> ft{{"finetune.py"}} --> model["model/"]
    data[("clean_dataset")] --> ft
    ft --> log["training_log.jsonl"]
```

#### 적합 상황

- effective_count 2K~10K건 + 패턴 반복성 확인
- 사전 학습된 base model이 있고, 도메인 적응이 필요한 경우
- classification, NER 등 표준 NLP 태스크

#### 실행 단계

1. **base_model 로드**: model-decision에서 결정된 `base_model`을 다운로드/로드
2. **데이터 전처리**: `clean_dataset.jsonl` → 모델별 토크나이저 형식으로 변환
   - train/validation split 적용 (Phase 1에서 준비된 splits/)
3. **파인튜닝 실행**: `finetune.py`
   - 기본 하이퍼파라미터:
     - learning_rate: 2e-5
     - batch_size: 16
     - epochs: 3~5 (early stopping with patience=2)
     - warmup_ratio: 0.1
   - 사용자가 하이퍼파라미터를 지정하면 그 값을 사용
4. **validation 평가**: epoch마다 validation loss + f1 측정
   - early stopping 조건: validation f1이 2 epoch 연속 하락
5. **모델 저장**: best checkpoint를 `model/`로 저장
6. **ONNX 변환** (선택): runtime이 `onnx`이면 변환 실행

#### 산출물

| 파일 | 경로 |
|------|------|
| model/ | `tl20_model/model/` (PyTorch 또는 ONNX) |
| tokenizer/ | `tl20_model/tokenizer/` |
| training_log.jsonl | `tl20_model/training_log.jsonl` |
| config.json | `tl20_model/config.json` (`training_route: "standard"`) |

---

### training_log.jsonl 형식

```jsonl
{"epoch": 1, "train_loss": 0.42, "val_loss": 0.38, "val_f1": 0.84, "lr": 2e-5, "training_route": "lora"}
{"epoch": 2, "train_loss": 0.28, "val_loss": 0.31, "val_f1": 0.89, "lr": 1.8e-5, "training_route": "lora"}
{"epoch": 3, "train_loss": 0.19, "val_loss": 0.29, "val_f1": 0.91, "lr": 1.6e-5, "training_route": "lora"}
```

### 경로 간 강등 정책

SetFit/LoRA가 Phase 4 평가에서 f1 기준 미달 시:

```
경로 A (SetFit) 실패 → 경로 B (LoRA) 시도 (데이터 충분 시)
경로 B (LoRA) 실패 → 경로 C (표준 FT) 시도 (데이터 충분 시)
경로 C (표준 FT) 실패 → TL 강등 정책 적용 (TL-10)
```

---

## TL-30 — 전체 학습 / 다단계 파인튜닝

```mermaid
flowchart LR
    data[("clean_dataset")] --> stage1{{"stage 1: pretrain"}} --> ckpt1["checkpoint_1/"]
    ckpt1 --> stage2{{"stage 2: finetune"}} --> ckpt2["checkpoint_2/"]
    ckpt2 --> stage3{{"stage 3: distill"}} --> model["model/"]
```

### 적합 상황

- 데이터 > 10K건 + 복잡한 태스크
- base model 없이 처음부터 학습하거나, 다단계 적응이 필요한 경우
- multi-class (≥ 20), 복합 NER, 복잡한 sequence tagging

### 실행 단계

1. **Stage 1 — Domain-Adaptive Pretraining (DAPT)** (선택)
   - 도메인 비라벨 텍스트로 MLM(Masked Language Model) 추가 사전 학습
   - 비라벨 텍스트가 10K건 이상일 때 권장 (SciBERT, BioBERT 등 도메인 BERT 전략)
   - 도메인 텍스트 미제공 시 건너뜀
   - `unlabeled_count` > 10K이면 자동 권고, 사용자 승인 후 실행
2. **Stage 2 — Task-specific Finetune**
   - Stage 1 checkpoint (또는 base_model)에서 태스크별 파인튜닝
   - TL-20과 동일한 프로세스, 단 epoch 수 확대 (5~10)
   - 하이퍼파라미터 탐색: grid search 또는 사용자 지정
3. **Stage 3 — Knowledge Distillation** (선택)
   - 큰 모델 → 작은 모델로 증류하여 inference 속도 향상
   - model_size_mb > 500MB일 때 자동 트리거
   - 증류 후 f1 하락이 5% 이내면 증류 모델 채택
4. **checkpoint 관리**: 각 stage의 best checkpoint를 보존

### 산출물

| 파일 | 경로 |
|------|------|
| model/ | `tl30_model/model/` (최종 모델) |
| tokenizer/ | `tl30_model/tokenizer/` |
| checkpoints/ | `tl30_model/checkpoints/stage{N}_best/` |
| training_log.jsonl | `tl30_model/training_log.jsonl` |
| distill_log.jsonl | `tl30_model/distill_log.jsonl` (Stage 3 실행 시) |
| config.json | `tl30_model/config.json` |

---

## TL 강등 정책

학습 실패 시 자동으로 낮은 TL로 강등하여 재시도한다.

```mermaid
flowchart TD
    TL30["TL-30 실행"] -->|"성공"| done(["완료"])
    TL30 -->|"ExecutionError"| log30["carry_over_issue 기록"]
    log30 --> TL20["TL-20 재시도"]
    TL20 -->|"성공"| done
    TL20 -->|"ExecutionError"| log20["carry_over_issue 기록"]
    log20 --> TL10["TL-10 강등"]
    TL10 -->|"성공"| done
    TL10 -->|"실패"| hitl["HITL 에스컬레이션"]
```

### 강등 시 carry_over_issues 기록

```json
{
  "original_tl": "TL-30",
  "demoted_to": "TL-20",
  "reason": "OOM: GPU 메모리 부족으로 Stage 2 실패",
  "timestamp": "2026-03-18T14:30:00Z"
}
```

---

## runtime 선택 가이드

| runtime | 적합 상황 | 비고 |
|---------|-----------|------|
| `rules` | TL-10 산출물 | rules.json 기반 결정론적 추론 |
| `onnx` | TL-20/30 + latency 최적화 | CPU 추론 최적, 크로스플랫폼 |
| `pytorch` | TL-20/30 + GPU 가용 | 유연성 높음, GPU 필요 |

Phase 5에서 `deploy_spec.json`의 `runtime` 필드에 기록한다. 사용자가 명시하지 않으면 TL-10은 `rules`, TL-20/30은 `onnx`를 기본값으로 사용한다.
