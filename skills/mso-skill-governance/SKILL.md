---
name: mso-skill-governance
description: |
  스킬 구조, CC 계약, 레지스트리 정합성을 검증한다.
  Use when skills are modified, before releases, or during integration testing.
disable-model-invocation: true
---

# mso-skill-governance

> 이 스킬은 pack 전체의 정합성 게이트키퍼이다.
> CC-01~CC-05 계약 검증, 구조 검사, AAOS 잔존 참조 탐지를 수행한다.

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **CC (Contract Coupling)** | 스킬 간 입출력 계약. CC-01~CC-05로 정의 |
| **governance status** | `ok` / `warn` / `fail`. fail 시 파이프라인 중단 |
| **finding** | 개별 검사 항목의 결과. level(fail/warn) + evidence 포함 |

---

## 실행 프로세스

### Phase 1: 구조 검사

1. 각 스킬 디렉토리에 필수 파일 존재 확인:
   - `SKILL.md`, `core.md`, `modules/modules_index.md`
2. SKILL.md 프론트매터에 `name`, `description`, `disable-model-invocation` 존재 확인
3. 누락 시 → `finding: fail`

**when_unsure**: 선택적 파일(references/, samples/) 누락은 `warn`으로 처리.

### Phase 2: CC 계약 검증

1. `config.yaml`의 `cc_contracts` 로딩
2. CC-01~CC-05 각각에 대해:
   - producer/consumer 스킬 명 일치 확인
   - required_output_keys / required_input_keys 존재 확인
   - expected_artifact 경로에 실제 파일 존재 확인 (runtime wiring)
3. 불일치 → `finding: fail` + evidence 기록

### Phase 3: AAOS 잔존 참조 탐지

1. `01.product/` 및 `02.test/` 전체에서 탐색:
   - `04_Agentic_AI_OS`, `@ref(`, `context_id`, `SKILL.meta.yaml`, `scope: swarm`
2. 발견 시 → `finding: warn` (AAOS 의존성 미제거)

### Phase 4: 리포트 생성

1. 모든 findings를 집계하여 `governance_report.md` 또는 JSON 생성
2. status 결정: fail이 1개 이상 → `fail`, warn만 → `warn`, 없음 → `ok`
3. JSON 모드 (`--json`): stdout에 구조화 결과 출력

**when_unsure**: 미분류 파일/구조는 `warn`으로 기록하고 수동 확인 권장.

**산출물**: `governance_report.md` + JSON summary

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| → | 전체 스킬 (00~07) | 구조 및 계약 정합성 검증 대상 |
| ← | `mso-observability` | 실행 패턴 기반 governance 강화 제안 수신 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| 전체 검증 실행 | `python3 scripts/validate_all.py` |
| CC 계약만 검증 | `python3 scripts/validate_cc_contracts.py --config config.yaml --json` |
| 스키마 검증 | `python3 scripts/validate_schemas.py --json` |
| 외부 의존성 확인 | `python3 scripts/check_deps.py --config config.yaml` |
| 거버넌스 규칙 상세 | `python3 scripts/validate_gov.py` |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
