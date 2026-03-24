# module.data-augmentation

> Phase 1.5(Label Strategy) 및 Phase 3(Training) 전처리 단계에서 호출되는 데이터 증강 모듈.
> 기존 라벨 데이터의 다양성을 높여 학습 효율을 극대화한다.

---

## 개요

라벨 데이터가 제한적일 때 **의미를 유지하면서 표현만 변형**하여 데이터를 증폭한다. 주요 목적:

1. 학습 데이터 다양성 확보
2. 클래스 불균형 보정
3. 모델 일반화 성능 향상

---

## 증강 전략 선택

| 전략 | 방식 | 비용 | 자연스러움 | 적합 상황 |
|------|------|------|-----------|----------|
| **EDA** | 유의어 교체, 랜덤 삽입/삭제/스왑 | 거의 없음 | 낮음~중간 | 빠른 실험, 1차 증강 |
| **Back-Translation** | 원문→타국어→재번역 | API 비용 | 높음 | 실전 서비스, 품질 우선 |
| **LLM Paraphrase** | GPT/Claude로 의미 보존 재표현 | API 비용 | 매우 높음 | 소량 데이터 (< 500), 고품질 |

### 자동 선택 규칙

```
if labeled_count < 100:
    strategy = ["llm_paraphrase"]           # 소량이므로 고품질 우선
elif labeled_count < 500:
    strategy = ["back_translation", "eda"]  # 혼합 전략
else:
    strategy = ["eda", "back_translation"]  # EDA 1차 + BT 보완
```

> 사용자가 전략을 직접 지정할 수 있다. 미지정 시 자동 선택.

---

## EDA (Easy Data Augmentation)

### 4가지 변형 기법

| 기법 | 설명 | 파라미터 |
|------|------|---------|
| **Synonym Replacement (SR)** | 단어를 유의어로 교체 | `sr_ratio`: 교체 비율 (기본 0.1) |
| **Random Insertion (RI)** | 관련 단어 추가 삽입 | `ri_ratio`: 삽입 비율 (기본 0.1) |
| **Random Swap (RS)** | 단어 위치 교체 | `rs_ratio`: 교체 비율 (기본 0.1) |
| **Random Deletion (RD)** | 일부 단어 삭제 | `rd_ratio`: 삭제 비율 (기본 0.1) |

### 실행

```python
# eda_augment.py 개념
def eda(text, alpha=0.1, num_aug=4):
    augmented = []
    augmented.append(synonym_replacement(text, alpha))
    augmented.append(random_insertion(text, alpha))
    augmented.append(random_swap(text, alpha))
    augmented.append(random_deletion(text, alpha))
    return augmented
```

### 한국어 지원

- 유의어 사전: KoWordNet 또는 LLM 기반 유의어 생성
- 형태소 분석기: mecab, konlpy 활용하여 의미 단위 보존

### 제약

- 문장 길이 < 5 토큰: 증강 건너뜀 (의미 손상 위험)
- 고유명사, 숫자, 코드: 변형 대상에서 제외

---

## Back-Translation

### 작동 원리

```
원문 (한국어) → 영어 번역 → 다시 한국어 번역
```

의미는 유지되지만 표현이 자연스럽게 변형된다.

### 실행

```python
# back_translate.py 개념
def back_translate(text, src="ko", pivot="en"):
    translated = translate(text, src, pivot)    # ko → en
    back = translate(translated, pivot, src)     # en → ko
    return back
```

### 번역 엔진 옵션

| 엔진 | 비용 | 품질 | 비고 |
|------|------|------|------|
| Google Translate API | 유료 | 높음 | 가장 안정적 |
| MarianMT (HuggingFace) | 무료 | 중간 | 로컬 실행 가능 |
| mBART | 무료 | 중간~높음 | 다국어 지원 |

### pivot 언어 다양화

- 단일 pivot (en)보다 복수 pivot (en, ja, zh) 사용 시 다양성 증가
- pivot당 1개 변형 → 원본 1개에서 3개 변형 생성

### 제약

- 도메인 전문 용어 왜곡 가능 → 도메인 용어 사전으로 사후 교정
- 번역 품질에 의존 → 번역 엔진이 도메인을 지원하는지 확인

---

## LLM Paraphrase

### 작동 원리

LLM에 원문과 라벨을 제공하고, 동일 의미의 다른 표현을 생성한다.

### 프롬프트 템플릿

```
다음 텍스트의 의미를 유지하면서 다르게 표현해주세요.
원문: "{text}"
라벨: {label}

규칙:
- 의미와 의도를 정확히 유지할 것
- 표현 방식, 어순, 어휘를 자연스럽게 변경할 것
- 도메인 전문 용어는 그대로 유지할 것
- 3개의 서로 다른 변형을 생성할 것
```

### 품질 관리

1. **NLI 일치도 검증**: 원문-변형 간 entailment 확률 ≥ 0.80
2. **중복 제거**: 원문과 cosine similarity > 0.95인 변형 제거 (너무 유사)
3. **다양성 확인**: 변형 간 cosine similarity < 0.90 확인
4. **도메인 용어 보존 확인**: 원문의 전문 용어가 변형에도 존재하는지 검사

### 제약

- API 비용 발생
- LLM 편향이 데이터에 내재화 가능
- 대량 생성 시 중복/패턴화 위험 → temperature 조정으로 완화

---

## 증강 적용 규칙

### 1. 클래스 불균형 우선 증강

```
target_count = max(class_distribution.values())  # 최다 클래스 기준
for class_name, count in class_distribution.items():
    deficit = target_count - count
    if deficit > 0:
        augment(class_name, num=deficit)  # 부족분만 증강
```

### 2. 증강 배수 제한

| 원본 라벨 수 | 최대 증강 배수 | 근거 |
|-------------|--------------|------|
| < 50 | 5배 | 소량일수록 다양성 효과 큼 |
| 50~500 | 3배 | 적정 수준 |
| 500+ | 2배 | 과증강 방지 |

### 3. 검증 데이터 증강 금지

**validation/test split은 절대 증강하지 않는다.** 증강은 train split에만 적용.

### 4. 증강 데이터 태깅

모든 증강 데이터에 메타데이터 태그를 부착한다:

```jsonl
{"text": "증강된 텍스트", "label": "intent_A", "source": "augmentation", "method": "back_translation", "original_id": "raw_0042"}
```

---

## 산출물

| 파일 | 경로 |
|------|------|
| augmented_dataset.jsonl | `{run_dir}/model-optimizer/augmented_dataset.jsonl` |
| augmentation_report.json | `{run_dir}/model-optimizer/augmentation_report.json` |

### augmentation_report.json 형식

```json
{
  "strategy": ["eda", "back_translation"],
  "original_count": 300,
  "augmented_count": 900,
  "total_count": 1200,
  "augmentation_ratio": 3.0,
  "class_balance_before": { "A": 120, "B": 100, "C": 80 },
  "class_balance_after": { "A": 400, "B": 400, "C": 400 },
  "quality_checks": {
    "nli_pass_rate": 0.94,
    "duplicate_removed": 12,
    "domain_term_preserved": 0.98
  }
}
```

---

## when_unsure

- 번역 API 실패: EDA로 fallback
- LLM Paraphrase API 실패: Back-Translation으로 fallback
- 증강 후 NLI 검증 통과율 < 70%: 해당 전략 중단 + warning
- 한국어 유의어 사전 미설치: LLM 기반 유의어 생성으로 대체

---

## Error Handling

| 상황 | 처리 |
|------|------|
| 번역 API 타임아웃 | 3회 재시도 후 EDA fallback |
| 증강 후 라벨 여전히 부족 | HITL 에스컬레이션 |
| 증강 품질 미달 (NLI < 0.70) | 해당 배치 폐기 + 다른 전략 시도 |
| 메모리 부족 (대규모 증강) | 배치 사이즈 축소 후 재시도 |
