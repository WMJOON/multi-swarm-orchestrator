# Schema History Snapshots

이 디렉토리는 `init.sql` 스키마의 버전별 스냅샷을 보관한다.

| 버전 | 파일 | 변경 요약 |
|------|------|-----------|
| 1.5.0 | `init_v1.5.0.sql` | WAL 모드, 8개 work tracking 컬럼, suggestion_history, 분석 뷰 3개 (v0.0.4) |

스냅샷은 마이그레이션 검증 및 롤백 참조용이다. 직접 실행하지 않는다.
