# mso-agent-audit-log

Claude Code Stop 이벤트에서 워크로그 작성을 유도하는 범용 훅 스킬.

## 제공 훅

| 파일 | 이벤트 | 설명 |
|------|--------|------|
| `hooks/stop_hook.sh` | Stop | 세션 종료 시 워크로그 미기록 여부 점검 |

## 프로젝트 연동 방법

`.claude/settings.json`의 `Stop` 훅에서 `WORKLOG_DIR`을 주입해 호출한다.

```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "WORKLOG_DIR=\"/your/project/agent_log/logs\" bash \"~/.skill-modules/mso-skills/mso-agent-audit-log/hooks/stop_hook.sh\"",
        "timeout": 10
      }
    ]
  }
]
```

## 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `WORKLOG_DIR` | ✅ | — | 워크로그 파일이 저장될 디렉터리 절대경로 |
| `WORKLOG_COOLDOWN_SEC` | — | `300` | 동일 파일 재프롬프트 방지 쿨다운(초) |

## 동작 흐름

1. `WORKLOG_DIR/worklog-{YYYYMMDD}.md` 경로 계산
2. 해당 파일이 `WORKLOG_COOLDOWN_SEC` 이내 수정됐으면 → 무시(exit 0)
3. 그 외 → `additionalContext`로 Claude에게 워크로그 작성 요청 주입
4. Claude가 워크로그 작성 후 다시 Stop → 2번에서 쿨다운 통과 → 조용히 종료
