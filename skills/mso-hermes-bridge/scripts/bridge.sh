#!/usr/bin/env bash
# mso-hermes-bridge/scripts/bridge.sh
# MSO에서 Hermes Agent로 태스크를 위임한다 (Runs API 폴링 방식).
#
# Usage:
#   bridge.sh "<task>" [--conversation <id>] [--timeout <seconds>]
#
# Exit codes:
#   0  성공 (output을 stdout으로 출력)
#   1  Hermes 미실행 또는 health check 실패
#   2  timeout 초과
#   3  Hermes run 실패 (status=failed)
#   4  인증 실패 (HTTP 401)

set -euo pipefail

HERMES_BASE="${HERMES_BASE:-http://127.0.0.1:8642}"
HERMES_KEY="${HERMES_API_KEY:-}"
TIMEOUT="${HERMES_TIMEOUT:-300}"
POLL_INTERVAL=5
CONVERSATION=""

# --- 인자 파싱 ---
TASK=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --conversation) CONVERSATION="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        *) TASK="$1"; shift ;;
    esac
done

if [[ -z "$TASK" ]]; then
    echo "[hermes-bridge] ERROR: task 인자가 없습니다" >&2
    echo "Usage: bridge.sh \"<task>\" [--conversation <id>] [--timeout <seconds>]" >&2
    exit 1
fi

if [[ -z "$HERMES_KEY" ]]; then
    echo "[hermes-bridge] ERROR: HERMES_API_KEY 환경변수가 설정되지 않았습니다" >&2
    exit 4
fi

# --- 1. Health check ---
HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "${HERMES_BASE}/v1/health" 2>/dev/null || echo "000")
if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "[hermes-bridge] ERROR: Hermes가 응답하지 않습니다 (${HERMES_BASE}/v1/health → ${HTTP_STATUS})" >&2
    echo "[hermes-bridge] 'hermes gateway'를 먼저 실행하세요" >&2
    exit 1
fi

# --- 2. Run 생성 ---
PAYLOAD="{\"input\": $(echo -n "$TASK" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
if [[ -n "$CONVERSATION" ]]; then
    PAYLOAD="${PAYLOAD}, \"conversation\": \"${CONVERSATION}\""
fi
PAYLOAD="${PAYLOAD}}"

RESPONSE=$(curl -sf -X POST "${HERMES_BASE}/v1/runs" 
    -H "Authorization: Bearer ${HERMES_KEY}" 
    -H "Content-Type: application/json" 
    -d "$PAYLOAD") || {
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${HERMES_BASE}/v1/runs" 
            -H "Authorization: Bearer ${HERMES_KEY}" 
            -H "Content-Type: application/json" 
            -d "$PAYLOAD")
        if [[ "$HTTP_CODE" == "401" ]]; then
            echo "[hermes-bridge] ERROR: 인증 실패 (401). HERMES_API_KEY를 확인하세요" >&2
            exit 4
        fi
        echo "[hermes-bridge] ERROR: run 생성 실패 (HTTP ${HTTP_CODE})" >&2
        exit 1
    }

RUN_ID=$(echo "$RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
echo "[hermes-bridge] run 시작: ${RUN_ID}" >&2

# --- 3. 폴링 ---
ELAPSED=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    RUN_STATE=$(curl -sf "${HERMES_BASE}/v1/runs/${RUN_ID}" 
        -H "Authorization: Bearer ${HERMES_KEY}") || {
        echo "[hermes-bridge] WARNING: 폴링 실패, 재시도..." >&2
        sleep $POLL_INTERVAL
        ELAPSED=$((ELAPSED + POLL_INTERVAL))
        continue
    }

    STATUS=$(echo "$RUN_STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))')

    case "$STATUS" in
        completed)
            echo "[hermes-bridge] 완료 (${ELAPSED}s)" >&2
            echo "$RUN_STATE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("output",""))'
            exit 0
            ;;
        failed)
            echo "[hermes-bridge] ERROR: Hermes run 실패" >&2
            echo "$RUN_STATE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("output",""))' >&2
            exit 3
            ;;
        cancelled)
            echo "[hermes-bridge] ERROR: run이 취소됨" >&2
            exit 3
            ;;
        started|running|*)
            echo "[hermes-bridge] 대기 중... (${ELAPSED}s / status=${STATUS})" >&2
            ;;
    esac

    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

# --- 4. Timeout ---
echo "[hermes-bridge] ERROR: timeout (${TIMEOUT}s 초과). run_id=${RUN_ID}" >&2
echo "[hermes-bridge] 수동 확인: curl ${HERMES_BASE}/v1/runs/${RUN_ID}" >&2
exit 2
