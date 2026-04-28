# module.contract-sync

## 검사 항목

- `schemas/cc_contracts.schema.json`에 CC-01~CC-05 존재
- 계약 필수 키(`producer`,`consumer`,`required_input_keys`,`required_output_keys`) 존재
- 버전 호환 정책(`schema_version`) 표시

## 규칙

- `01~07` 스킬 스키마가 없으면 fail
- required key 미존재 시 fail
- 호환 정책이 없는 경우 warn + 수동 승인 유도
