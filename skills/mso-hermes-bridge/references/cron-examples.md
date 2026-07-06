# MSO Hermes Bridge — Cron 설정 예시

Hermes를 MSO workflow 정기 실행에 쓰는 crontab 패턴 모음.

---

## 기본 구조

```bash
# crontab -e
# ┌─ 분 ┬─ 시 ┬─ 일 ┬─ 월 ┬─ 요일
# │     │     │     │     │
# *     *     *     *     *   command
```

---

## 패턴 1 — 매일 정기 분석

```bash
# 매일 오전 9시: 프로젝트 상태 분석 → artifact 저장
0 9 * * * cd ~/projects/my-project && \
  HERMES_API_KEY=your-key \
  bash skills/mso-hermes-bridge/scripts/bridge.sh \
    "MSO 프로젝트 상태를 점검하고 agent-context/artifacts/daily-status.md 에 기록해" \
    --conversation mso-daily \
    --timeout 600 \
  >> logs/hermes-daily.log 2>&1
```

---

## 패턴 2 — 주간 workflow 실행

```bash
# 매주 월요일 오전 8시: 주간 워크플로우
0 8 * * 1 cd ~/projects/my-project && \
  STEP_CONTEXT=$(python3 skills/mso-hermes-bridge/scripts/workflow_context.py \
    --workflow-dir agent-context/workflow \
    --step-id weekly-review \
    --format prompt) && \
  HERMES_API_KEY=your-key \
  bash skills/mso-hermes-bridge/scripts/bridge.sh "$STEP_CONTEXT" \
    --conversation mso-weekly \
  >> logs/hermes-weekly.log 2>&1
```

---

## 패턴 3 — 매시간 헬스체크 (경량)

```bash
# 매시간 정각: Hermes 살아있는지 확인
0 * * * * curl -sf http://127.0.0.1:8642/health > /dev/null || \
  osascript -e 'display notification "Hermes 다운" with title "MSO Alert"'
```

---

## 패턴 4 — 결과를 Artifact로 저장

```bash
# 매일 자정: 일간 요약 → wf:Artifact에 materialize
0 0 * * * cd ~/projects/my-project && \
  OUTPUT=$(HERMES_API_KEY=your-key \
    bash skills/mso-hermes-bridge/scripts/bridge.sh \
      "오늘 작업 로그를 요약해" --conversation mso-daily) && \
  echo "$OUTPUT" > agent-context/artifacts/summary-$(date +%Y%m%d).md && \
  echo "Saved: $(date)" >> logs/artifact-saves.log
```

---

## 패턴 5 — 멀티 에이전트 순차 실행

```bash
# Hermes → Codex 순서로 실행 (하이브리드)
30 9 * * * cd ~/projects/my-project && \
  # Step 1: Hermes로 분석
  HERMES_OUT=$(HERMES_API_KEY=your-key \
    bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청" \
      --conversation mso-hybrid) && \
  # Step 2: Codex로 코드 수정 제안
  echo "$HERMES_OUT" | \
    python3 skills/mso-codex-bridge/scripts/codex_bridge.py sync - \
  >> logs/hybrid-daily.log 2>&1
```

---

## launchd 방식 (macOS 권장)

crontab 대신 `~/Library/LaunchAgents/` plist 사용 — 절전 복귀 후에도 안정적.

```xml
<!-- ~/Library/LaunchAgents/mso.hermes.daily.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>mso.hermes.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/you/projects/my-project/skills/mso-hermes-bridge/scripts/bridge.sh</string>
    <string>MSO 일간 분석 수행</string>
    <string>--conversation</string>
    <string>mso-daily</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HERMES_API_KEY</key>
    <string>your-local-key</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/mso-hermes-daily.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/mso-hermes-daily.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/mso.hermes.daily.plist
```

---

## 주의사항

- `HERMES_API_KEY`는 crontab에 직접 넣지 말고 `.env` 소싱 권장
- `hermes gateway`가 실행 중이어야 함 (launchd 데몬으로 등록 권장)
- 로그 로테이션: `logrotate` 또는 `newsyslog` 설정 추가
