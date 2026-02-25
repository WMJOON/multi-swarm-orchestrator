---
name: mso-agent-audit-log
version: 0.0.4
run_input: "run-manifest, task context event, behavior events, node snapshots"
run_output: "sqlite rows in audit_logs, decision graph tables, and node_snapshots"
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
  - `node_snapshot` (선택적)
    - `node_id`, `node_type` (commit|branch|merge)
    - `parent_refs` (JSON array)
    - `tree_hash_type`, `tree_hash_ref`
    - `agent_role` (provisioning|execution|handoff|branching|critic_judge|sentinel)
    - `phase` (1-4)
    - `merge_policy` (merge 노드 전용, JSON)
    - `fallback_target` (절대 SHA 참조)
  - v0.0.4 확장 필드 (선택적)
    - `work_type` (execution|modification|structure|document|skill|error|review|workflow_optimization)
    - `triggered_by` (user_request|auto|hook)
    - `duration_sec` (REAL)
    - `files_affected` (JSON array)
    - `sprint` (TEXT)
    - `pattern_tag` (TEXT)
    - `session_id` (TEXT)
    - `intent` (TEXT)

## 출력
- `audit_logs` 행, `decisions`, `evidence`, `impacts`, `document_references` 테이블의 가시적 갱신
- `node_snapshots` 행: node_type, parent_refs, tree_hash_ref, agent_role, phase, status 기록
- `suggestion_history` 행 (v0.0.4): 패턴 제안, 사용자 승인/거절 이력 기록
- 수동 승인 요청이 필요한 경우 `notes`/`continuation_hint`로 힌트 기록

## 공통 출력 형태

```json
{
  "run_id": "20260220-msoal-audit-sample",
  "artifact_uri": "workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json",
  "status": "success | fail | in_progress",
  "errors": ["..."] ,
  "warnings": ["..."],
  "next_actions": ["..."],
  "metadata": {
    "schema_version": "1.5.0",
    "producer": "mso-agent-audit-log"
  },
  "work_type": "execution",
  "triggered_by": "auto",
  "duration_sec": 5.2,
  "files_affected": ["outputs/execution_plan.json"],
  "sprint": null,
  "pattern_tag": null,
  "session_id": "sess-001",
  "intent": "Pipeline node execution",
  "node_snapshot": {
    "node_id": "node_01",
    "node_type": "commit",
    "parent_refs": [],
    "tree_hash_type": "sha256",
    "tree_hash_ref": null,
    "agent_role": "execution",
    "phase": 2,
    "status": "committed"
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
