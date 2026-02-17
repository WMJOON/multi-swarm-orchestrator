---
name: mso-agent-audit-log
version: 0.0.2
run_input: "run-manifest, task context event, behavior events"
run_output: "sqlite rows in audit_logs and decision graph tables"
status_model: "success | fail | in_progress"
---

# Core

## 목적
이 스킬은 에이전트 오퍼레이션의 감사 추적 SoT를 담당한다.
`mso-agent-audit-log`는 로그 표준화를 소유하고, 다른 스킬은 이를 소비만 한다.

## 입력
- 입력 객체(권장)
  - `run_id` (필수)
  - `artifact_uri` (필수)
  - `status`, `errors`, `warnings`, `next_actions` (기본 필드)
  - `metadata` (`schema_version` 포함 권장)

## 출력
- `audit_logs` 행, `decisions`, `evidence`, `impacts`, `document_references` 테이블의 가시적 갱신
- 수동 승인 요청이 필요한 경우 `notes`/`continuation_hint`로 힌트 기록

## 공통 출력 형태

```json
{
  "run_id": "20260217-msoal-audit-sample",
  "artifact_uri": "workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json",
  "status": "success | fail | in_progress",
  "errors": ["..."] ,
  "warnings": ["..."],
  "next_actions": ["..."],
  "metadata": {
    "schema_version": "1.3.0",
    "producer": "mso-agent-audit-log"
  }
}
```

## 계약 우선순위
1. SoT 스키마
2. 본 스킬 `SKILL.md`
3. 소비자 요청(JSON payload)

## 실패 모드
- 필수 필드 누락: 경고 기록 후 보조 필드로 정리
- 쓰기 실패: status `fail`로 기록하고 파이프라인은 중단하지 않으며 fallback 채널 안내

## 보안
- `notes`에는 사용자 토큰/패스워드/PII를 직접 저장하지 않는다.
- 민감 증거는 `context` 또는 별도 파일 경로로 인덱싱만 남긴다.
