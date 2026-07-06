#!/usr/bin/env bash
# mso-hermes-bridge/hooks/hermes-repo-setup.sh
#
# MSO repository init 시 Hermes 세팅을 함께 구성한다.
# mso-repository-setup의 init.py --hermes 플래그 또는
# 단독으로 실행 가능하다.
#
# Usage:
#   bash skills/mso-hermes-bridge/hooks/hermes-repo-setup.sh [--root <project-root>]
#
# 동작:
#   1. .hermes/ 디렉토리를 프로젝트 루트에 생성
#   2. hermes-project-context.md를 .hermes/mso-context.md로 배포
#   3. ~/.hermes/.env에 API_SERVER_ENABLED 확인/안내
#   4. HERMES_API_KEY 확인 및 안내

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="${1:-$(pwd)}"
MSO_VERSION="0.8.0"

# --root 파싱
while [[ $# -gt 0 ]]; do
    case "$1" in
        --root) PROJECT_ROOT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "[hermes-setup] MSO 프로젝트: $PROJECT_ROOT"

# --- 1. .hermes/ 디렉토리 생성 ---
HERMES_DIR="$PROJECT_ROOT/.hermes"
mkdir -p "$HERMES_DIR"
echo "[hermes-setup] .hermes/ 생성 완료"

# --- 2. Hermes 프로젝트 컨텍스트 배포 ---
TMPL="$SKILL_DIR/references/hermes-project-context.md.tmpl"
DEST="$HERMES_DIR/mso-context.md"

if [[ ! -f "$TMPL" ]]; then
    echo "[hermes-setup] ERROR: 템플릿 없음: $TMPL" >&2
    exit 1
fi

INIT_DATE=$(date +"%Y-%m-%d")
sed \
    -e "s|{{MSO_VERSION}}|$MSO_VERSION|g" \
    -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
    -e "s|{{INIT_DATE}}|$INIT_DATE|g" \
    "$TMPL" > "$DEST"

echo "[hermes-setup] .hermes/mso-context.md 배포 완료"

# --- 3. bridge.sh 심볼릭 링크 (편의용) ---
BRIDGE_SRC="$SKILL_DIR/scripts/bridge.sh"
BRIDGE_LINK="$PROJECT_ROOT/.hermes/bridge.sh"
if [[ -f "$BRIDGE_SRC" ]] && [[ ! -e "$BRIDGE_LINK" ]]; then
    ln -s "$BRIDGE_SRC" "$BRIDGE_LINK"
    echo "[hermes-setup] .hermes/bridge.sh 심볼릭 링크 생성"
fi

# --- 4. Hermes API Server 설정 확인 ---
HERMES_ENV="$HOME/.hermes/.env"
echo ""
echo "[hermes-setup] ── Hermes API Server 설정 확인 ──"

if [[ -f "$HERMES_ENV" ]]; then
    if grep -q "API_SERVER_ENABLED=true" "$HERMES_ENV" 2>/dev/null; then
        echo "[hermes-setup] ? API_SERVER_ENABLED=true 확인"
    else
        echo "[hermes-setup] ?  ~/.hermes/.env에 API_SERVER_ENABLED=true 추가 필요:"
        echo "    echo 'API_SERVER_ENABLED=true' >> ~/.hermes/.env"
    fi
    if grep -q "API_SERVER_KEY=" "$HERMES_ENV" 2>/dev/null; then
        echo "[hermes-setup] ? API_SERVER_KEY 설정 확인"
    else
        echo "[hermes-setup] ?  ~/.hermes/.env에 API_SERVER_KEY 추가 필요:"
        echo "    echo 'API_SERVER_KEY=your-local-key' >> ~/.hermes/.env"
    fi
else
    echo "[hermes-setup] ?  ~/.hermes/.env 없음. Hermes 설치 또는 설정 필요:"
    echo "    echo 'API_SERVER_ENABLED=true' > ~/.hermes/.env"
    echo "    echo 'API_SERVER_KEY=your-local-key' >> ~/.hermes/.env"
fi

# --- 5. HERMES_API_KEY 환경변수 확인 ---
if [[ -z "${HERMES_API_KEY:-}" ]]; then
    echo "[hermes-setup] ?  HERMES_API_KEY 환경변수 미설정"
    echo "    export HERMES_API_KEY=your-local-key  # ~/.zshrc에 추가 권장"
else
    echo "[hermes-setup] ? HERMES_API_KEY 환경변수 확인"
fi

echo ""
echo "[hermes-setup] 완료. Hermes 시작: hermes gateway"
echo "[hermes-setup] 위임 실행:"
echo "    bash .hermes/bridge.sh \"태스크 설명\" --conversation mso-$(basename $PROJECT_ROOT)"
