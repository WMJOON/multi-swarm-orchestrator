# module.schema-contract

## 질문 축

- 로그 스키마의 소유권과 변경 경로는 어디까지인가?

## 규칙

- SoT 스키마는 `schema/init.sql`, `schema/migrate_v1_to_v1_1.sql`로 단일 관리.
- 다른 스킬은 스키마를 재정의할 수 없다.
- `task_name`, `status`, `action`, `id` 필드는 비워둘 수 없다.
- 결정/증거 엔티티(`decisions`, `evidence`, `impacts`)는 `id` 기반의 연결 관계를 보존한다.
- 스키마 버전은 `metadata.schema_version`으로 기록한다.
