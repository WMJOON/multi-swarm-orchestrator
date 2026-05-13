# mso-agent-audit-log

세션 생명주기 이벤트에서 워크로그 기록과 컨텍스트 주입을 담당하는 감사 훅 스킬.

## 제공 훅

| 파일 | 이벤트 | 설명 |
|------|--------|------|
| `hooks/session_start_hook.sh` | SessionStart | 세션 시작 시 최신 워크로그 3개를 컨텍스트에 주입 |
| `hooks/pre_compact_hook.sh` | PreCompact | 컨텍스트 압축 직전 워크로그 미기록 여부 점검 |
| `hooks/session_end_hook.sh` | SessionEnd | 세션 종료 시 워크로그 미기록 여부 점검 |

> `hooks/stop_hook.sh` (Stop) — deprecated. Stop 이벤트는 루프 발생 및 기록 시점 부적합으로 사용하지 않는다.

## 프로젝트 연동 방법

`.claude/settings.json`의 훅 섹션에 세 이벤트를 등록한다. `WORKLOG_DIR`을 각 프로젝트의 로그 디렉터리로 교체한다.

```json
"hooks": {
  "SessionStart": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "WORKLOG_DIR=\"/your/project/00.agent_log/logs\" bash \"~/.skill-modules/mso-skills/mso-agent-audit-log/hooks/session_start_hook.sh\"",
          "timeout": 10
        }
      ]
    }
  ],
  "PreCompact": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "WORKLOG_DIR=\"/your/project/00.agent_log/logs\" bash \"~/.skill-modules/mso-skills/mso-agent-audit-log/hooks/pre_compact_hook.sh\"",
          "timeout": 10
        }
      ]
    }
  ],
  "SessionEnd": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "WORKLOG_DIR=\"/your/project/00.agent_log/logs\" bash \"~/.skill-modules/mso-skills/mso-agent-audit-log/hooks/session_end_hook.sh\"",
          "timeout": 10
        }
      ]
    }
  ]
}
```

## 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `WORKLOG_DIR` | ✅ | — | 워크로그 파일이 저장될 디렉터리 절대경로 |
| `WORKLOG_COOLDOWN_SEC` | — | `300` | 동일 파일 재프롬프트 방지 쿨다운 (PreCompact·SessionEnd) |

## 동작 흐름

### SessionStart
1. `WORKLOG_DIR/worklog-*.md` 파일을 최신순으로 최대 3개 탐색
2. 각 파일의 앞 80줄을 읽어 `additionalContext`로 조합
3. Claude 세션 시작 시 이전 세션 맥락으로 주입

### PreCompact
1. `WORKLOG_DIR/worklog-{YYYYMMDD}.md` 경로 계산
2. 해당 파일이 `WORKLOG_COOLDOWN_SEC` 이내 수정됐으면 → 무시 (exit 0)
3. 그 외 → 컴팩션 직전 워크로그 기록 요청 주입
4. 컨텍스트가 압축되기 전에 현재 세션 상태를 기록할 수 있는 최적 시점

### SessionEnd
1. `WORKLOG_DIR/worklog-{YYYYMMDD}.md` 경로 계산
2. 해당 파일이 `WORKLOG_COOLDOWN_SEC` 이내 수정됐으면 → 무시 (exit 0)
3. 그 외 → 세션 종료 직전 워크로그 기록 요청 주입
