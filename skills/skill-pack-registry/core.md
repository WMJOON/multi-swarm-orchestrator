---
name: skill-pack-registry
version: 0.1.0
layer: meta
---

# Core

## 목적
스킬 팩(mso, msm 등)의 prefix, required_skills, overload_threshold를 중앙 관리한다.
validate_gov.py가 --pack 인자로 이 레지스트리를 읽어 팩별로 독립 검증한다.

## 입력/출력
- 입력: pack_id (예: mso, msm)
- 출력: prefix, required_skills[], overload_threshold, version

## 상태 모델
- references/pack_registry.json이 단일 소스
- 팩 추가/수정 시 이 파일만 편집
