---
name: mso-skill-governance
version: 0.0.1
layer: operational
---

# Core

## 목적
00~07 스킬의 구조, 계약(CC), 레지스트리 정합을 검증해 파이프라인 안정성을 확보한다.

## 검사 범위
- 필수 파일 존재 (`core.md`, `modules/modules_index.md`, `references/source_map.md`, `scripts/...`)
- 스킬 간 CC 계약 정의(`schemas/cc_contracts.schema.json`) 정합
- AAOS 특화 고정 경로 사용 여부
- profile 기반 스킬 집합 과부하 경고

## 입력/출력
- 입력: 스킬 폴더, `v0.0.1/config.yaml`, 계약 스키마
- 출력: `references/governance_report.md`, JSON summary(`--json`)

## 상태 모델
- `status`: `ok | warn | fail`
- `findings`: 항목별 판단/근거/트레이드오프/확신도

## 실패 규칙
- 고정 required 파일 누락이나 CC 필수 키 누락은 `fail`.
- AAOS 고정 문자열 사용, duplicate skill_ids는 `warn`.
- 스키마/계약 미스매치가 누적되면 fail-fast.
