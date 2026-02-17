---
name: mso-agent-audit-log
description: |
  에이전트 실행 로그를 SQLite SoT로 표준화한다.
  Use when an execution result, run-manifest, or dispatch output needs audit trail recording.
disable-model-invocation: true
---

# mso-agent-audit-log

> 이 스킬은 감사 로그 스키마의 유일한 소유자(SoT)이다.
> 다른 스킬은 이 DB를 소비만 할 수 있으며, 쓰기는 반드시 이 스킬을 통해야 한다.

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **SoT** | `workspace/.mso-context/active/<Run ID>/50_audit/agent_log.db` (SQLite). 모든 감사 데이터의 단일 진실 원천 |
| **audit payload** | `run_id`, `artifact_uri`, `status`, `errors`, `warnings`, `next_actions`, `metadata` |
| **schema_version** | 현재 `1.3.0`. 테이블: `audit_logs`, `decisions`, `evidence`, `impacts`, `document_references` |

---

## 실행 프로세스

### Phase 1: 입력 수신 및 검증

1. 입력 payload를 수신한다 (JSON 또는 Python dict)
2. 필수 키 확인: `run_id`, `artifact_uri`, `status`
3. 누락 시 → 경고 기록 후 보조 필드로 빈값 채움 (fail-fast 아님)

**when_unsure**: `run_id`가 없으면 타임스탬프 기반 임시 ID 생성 후 warning 기록.

### Phase 2: SoT 기록

1. `workspace/.mso-context/active/<Run ID>/50_audit/agent_log.db`에 연결 (경로: config.yaml `audit_log.db_path`)
2. DB 미존재 시 → `scripts/init_db.py`로 스키마 초기화
3. `audit_logs` 테이블에 INSERT
4. `decisions`, `evidence` 등 보조 테이블은 payload에 해당 필드 존재 시에만 기록

### Phase 3: 결과 확인

1. INSERT 성공 → `status: success` 반환
2. 쓰기 실패 → `status: fail` 기록, 파이프라인은 중단하지 않고 fallback 채널 안내

**산출물**: audit payload JSON (CC-05 출력으로 observability가 소비)

---

## 보안

- `notes`에 사용자 토큰/패스워드/PII를 평문 저장하지 않는다
- 민감 증거는 파일 경로로 인덱싱만 남긴다

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-execution-design` | 실행 결과 로그 수신 |
| ← | `mso-agent-collaboration` | CC-04: dispatch 결과를 audit payload로 수신 |
| → | `mso-observability` | CC-05: audit DB를 읽기 전용으로 제공 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| DB 스키마 초기화 | `python3 scripts/init_db.py` |
| payload로 행 추가 | `python3 scripts/append_from_payload.py --payload <json>` |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
