# Modules Index

## 직교 질문 축

| Module | Question Axis | 목적 |
|---|---|---|
| module.schema-contract | 로그 스키마와 마이그레이션 정책 | 스키마 오너십 명시 |
| module.ingest-runs | 런/콜백 이벤트 적재 규칙 | 파이프라인 연동 입력 수집 |
| module.decision-tree | 결정/증거/영향 트리 | 사용 추적성 확보 |

## 모듈 레지스트리

| Module | File |
|---|---|
| module.schema-contract | `modules/module.schema-contract.md` |
| module.ingest-runs | `modules/module.ingest-runs.md` |
| module.decision-tree | `modules/module.decision-tree.md` |

## 로딩 규칙

- 기본 로딩: `module.schema-contract`
- CC 연동 시 `module.ingest-runs`
- 감사/회고 시 `module.decision-tree`
