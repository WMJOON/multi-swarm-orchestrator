# Changelog

## v0.1.0 (2026-03-24)

Label Strategy + PEFT 통합 릴리스. 소량 라벨 환경에서의 모델 생산 능력을 대폭 강화.

### Added

- **Phase 1.5: Label Strategy (LS-0~3)**
  - LS-0: Zero-shot NLI → Clustering → HITL 검증 → LLM 합성 보충
  - LS-1: kNN baseline + Cleanlab 감사 + Data Augmentation
  - LS-2: Active Learning (Uncertainty Sampling) + Augmentation
  - LS-3: 충분한 라벨 → Phase 2 직행
  - 라벨 0개 상태에서도 모델 학습 파이프라인 진입 가능
  - `min_per_class == 0` 엣지케이스 처리 (일부 클래스 라벨 부재)
  - LS-0 조기 탈출: Zero-shot 신뢰도 5% 미만 시 즉시 HITL 에스컬레이션

- **module.data-augmentation.md**
  - EDA (Synonym Replacement, Random Insertion/Swap/Deletion)
  - Back-Translation (다국어 pivot 지원)
  - LLM Paraphrase (NLI 일치도 검증 포함)
  - 클래스 불균형 우선 증강, 증강 배수 제한
  - 자동 전략 선택 (라벨 수 기반)

- **TL-20 3경로 라우팅**
  - 경로 A: SetFit (effective_count 50~200, 클래스당 8개로 GPT-3급)
  - 경로 B: LoRA/QLoRA (effective_count 200~2K, VRAM 10~20배 절감)
  - 경로 C: 표준 Fine-tuning (effective_count 2K~10K)
  - NER/tagging 태스크 per-entity 오버라이드 규칙
  - 경로 간 강등 정책 (SetFit → LoRA → 표준 FT → TL-10)

- **Signal A 확장**
  - `labeled_count` + `unlabeled_count` 분리
  - `effective_count` = labeled + 0.7 × (augmented + weak + synthetic)
  - 라벨 소스 품질 가중치 (인간=1.0, 증강=0.7, 합성=0.5, pseudo=0.3)
  - Cleanlab 감사 데이터 +0.1 보정
  - SetFit 조건: `labeled_count(인간 검증만) ≥ 8/class`

- **임베딩 캐싱**
  - kNN baseline 단계에서 계산된 임베딩을 `embeddings_cache.npy`로 저장
  - Phase 4 평가, Clustering, Active Learning에서 재사용

- **deploy_spec 확장**
  - `reproducibility` 블록에 `labeled_count`, `augmented_count`, `effective_count`, `label_strategy`, `training_route` 필드 추가

- **README.md + docs/** 디렉토리 신설

### Changed

- **Signal A**: `total_count` 단일 기준 → `effective_count` + 라벨 소스 가중치 기반
- **TL-20**: 단일 fine-tuning → 3경로 라우팅 (SetFit/LoRA/표준)
- **TL-30 Stage 1**: "Domain Pretrain" → "Domain-Adaptive Pretraining (DAPT)" 명시, `unlabeled_count > 10K` 자동 권고
- **core.md**: 용어 5개 추가 (LS, effective_count, SetFit, LoRA/QLoRA), Processing Rules 13개로 확장
- **Error Handling**: 데이터 부족 시 Label Strategy(LS-0) 시도 후 TL-10 강등 (기존: 즉시 TL-10)
- **Quick Example**: Phase 1.5 포함, LoRA 경로 시연

### Fixed

- (N/A — 첫 릴리스 기준)

---

## v0.0.1 (2026-03-18)

초기 버전. 5-Phase 파이프라인 + TL-10/20/30 + deploy_spec 기본 구조.

- Phase 0~5 실행 프로세스 정의
- model-decision 3-Signal (A: 데이터 가용성, B: 태스크 특성, C: 모델 이력)
- TL-10 (Rule), TL-20 (표준 Fine-tuning), TL-30 (다단계 학습 + Distillation)
- deploy_spec.json + rollback 정책
- model-retraining (data drift 감지)
- Smart Tool manifest 스키마
