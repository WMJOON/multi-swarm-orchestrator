#!/usr/bin/env bash
# tools/build.sh — LinkML 3종 빌드 (M1 DoD)
# 사용: cd repository-test/skills/mso-intent-registry && bash tools/build.sh
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMA="$SKILL_DIR/references/schemas/nlu_intent.yaml"
OUT="$SKILL_DIR/generated"
mkdir -p "$OUT"

echo "[linkml build] schema: $SCHEMA"
echo ""

echo "[1/3] gen-owl ..."
gen-owl "$SCHEMA" > "$OUT/nlu_intent.owl.ttl"
echo "  → $OUT/nlu_intent.owl.ttl"

echo "[2/3] gen-shacl ..."
gen-shacl "$SCHEMA" > "$OUT/nlu_intent.shacl.ttl"
echo "  → $OUT/nlu_intent.shacl.ttl"

echo "[3/3] gen-json-schema ..."
gen-json-schema "$SCHEMA" > "$OUT/nlu_intent.schema.json"
echo "  → $OUT/nlu_intent.schema.json"

echo ""
echo "[verify] NodeShape count:"
grep -c "sh:NodeShape" "$OUT/nlu_intent.shacl.ttl" || true

echo ""
echo "Build OK — $OUT/"
