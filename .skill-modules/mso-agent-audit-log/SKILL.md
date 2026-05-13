---
name: mso-agent-audit-log
description: |
  Audit infrastructure owner for MSO. Owns DB creation, session hook setup, and audit trail recording.
  Use when initializing a new project environment, injecting session hooks into .claude/settings.json,
  or recording execution results into the SQLite SoT (audit_global.db).
  Triggers: "audit 초기화", "훅 세팅", "레포 환경 세팅", "audit-log setup",
  "DB init", "session hooks", "audit trail", "실행 로그 기록".
---

# mso-agent-audit-log

> 이 스킬은 MSO 감사 인프라의 유일한 소유자(SoT)이다.
> **DB 생성**, **세션 훅 설정**, **실행 로그 기록** 세 가지 책임을 모두 가진다.
> 다른 스킬은 이 DB를 소비만 할 수 있으며, 쓰기는 반드시 이 스킬을 통해야 한다.

---

## 책임 범위

| 책임 | 설명 |
|------|------|
| **환경 초기화** | audit DB 생성, 워크로그 디렉터리 생성, 세션 훅 주입 |
| **세션 훅** | SessionStart(컨텍스트 주입) · PreCompact(기록 촉구) · SessionEnd(최종 기록) |
| **로그 기록** | `audit_global.db`에 실행 결과 INSERT |

---

## 환경 초기화 (레포 설정 시 1회 실행)

```bash
python3 ~/.skill-modules/mso-skills/mso-agent-audit-log/scripts/setup.py \
  --project-root <workspace_root> \
  [--worklog-dir <path>] \
  [--db <path>] \
  [--dry-run]
```

한 번에 수행하는 작업:
1. `{project-root}/00.agent_log/logs/` 디렉터리 생성
2. `{project-root}/.mso-context/audit_global.db` 스키마 초기화 (migrate 포함)
3. `{project-root}/.claude/settings.json`에 세션 훅 주입 (멱등)

---

## 세션 훅

Claude 호출 없이 스크립트가 직접 기록·주입 — 토큰 소비 없음.

| 이벤트 | 스크립트 | 동작 방식 |
|--------|----------|-----------|
| `SessionStart` | `hooks/session_start_hook.py` | 최근 worklog 3개 마지막 항목 → compact 요약 주입 |
| `PreCompact` | `hooks/pre_compact_hook.py` | transcript 파싱 → worklog에 checkpoint 직접 기록 |
| `SessionEnd` | `hooks/session_end_hook.py` | transcript 파싱 → worklog에 세션 항목 직접 기록 |

- **Claude Code**: 세 이벤트 모두 `.claude/settings.json`에 등록
- **Codex**: `SessionStart`만 `.codex/hooks.json`에 등록 (PreCompact·SessionEnd 미지원)
- `session_start_hook.py`는 stdin의 `model` 필드로 런타임을 자동 감지해 출력 포맷 전환
  - Claude Code → `{"hookSpecificOutput": {"additionalContext": "..."}}`
  - Codex → `{"systemMessage": "..."}`

환경변수 `WORKLOG_DIR`로 워크로그 경로를 지정한다 (setup.py가 자동 설정).

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **SoT** | `{workspace}/.mso-context/audit_global.db` (SQLite) |
| **audit payload** | `run_id`, `artifact_uri`, `status`, `errors`, `warnings`, `next_actions`, `metadata` |
| **schema_version** | 현재 `1.5.0`. 테이블: `audit_logs`, `decisions`, `evidence`, `impacts`, `document_references`, `user_feedback`, `node_snapshots`, `suggestion_history` |

---

## 로그 기록 프로세스

### Phase 1: 입력 수신 및 검증

1. 입력 payload를 수신한다 (JSON 또는 Python dict)
2. 필수 키 확인: `run_id`, `artifact_uri`, `status`
3. 누락 시 → 경고 기록 후 보조 필드로 빈값 채움 (fail-fast 아님)

**when_unsure**: `run_id`가 없으면 타임스탬프 기반 임시 ID 생성 후 warning 기록.

### Phase 2a: SoT 기록

1. `{workspace}/.mso-context/audit_global.db`에 연결 (global DB 기본 경로)
2. DB 미존재 시 → `scripts/setup.py`로 환경 초기화
3. `audit_logs` 테이블에 INSERT
4. `decisions`, `evidence` 등 보조 테이블은 payload에 해당 필드 존재 시에만 기록

### Phase 2b: 스냅샷 기록

1. 입력에 `node_type`, `parent_refs`, `tree_hash_ref` 필드가 포함된 경우 스냅샷 기록
2. `node_snapshots` 테이블에 INSERT

### Phase 3: 결과 확인

1. INSERT 성공 → `status: success` 반환
2. 쓰기 실패 → `status: fail` 기록, 파이프라인은 중단하지 않고 fallback 채널 안내

---

## 보안

- `notes`에 사용자 토큰/패스워드/PII를 평문 저장하지 않는다
- 민감 증거는 파일 경로로 인덱싱만 남긴다

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-repository-setup` | 레포 환경 세팅 시 `setup.py` 호출 |
| ← | `mso-task-execution` | CC-06: execution_graph 노드 → 스냅샷 기록 |
| ← | `mso-agent-collaboration` | CC-04: dispatch 결과를 audit payload로 수신 |
| ← | `mso-workflow-optimizer` | CC-08: decision_output + HITL 피드백 기록 |
| → | `mso-observability` | CC-05: audit DB를 읽기 전용으로 제공 |

---

## 상세 파일 참조

| 상황 | 명령 |
|------|------|
| 환경 초기화 (DB + 훅) | `python3 {mso-agent-audit-log}/scripts/setup.py --project-root <path> [--target claude\|codex\|all]` |
| DB만 초기화 | `python3 {mso-agent-audit-log}/scripts/init_db.py` |
| 훅만 주입 | `python3 {mso-agent-audit-log}/scripts/inject_hooks.py --project-root <path> [--target claude\|codex\|all]` |
| payload로 행 추가 | `python3 {mso-agent-audit-log}/scripts/append_from_payload.py --payload <json>` |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
