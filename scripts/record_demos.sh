#!/usr/bin/env bash
# PM (Publication Media) — 全 12 demo を asciinema で録画する skeleton.
#
# 使い方:
#   ./scripts/record_demos.sh ja        # ja 言語版を 12 件すべて録画
#   ./scripts/record_demos.sh en --only resident-cognition
#
# 出力: docs/media/<scenario>_<lang>.cast
#
# 前提: asciinema (https://asciinema.org) と llive-demo が install 済み.
#   pip install asciinema
#   pip install -e .
#
# README に embed する場合は <a href="..."><img src="..."/></a> 形式か、
# Mintlify では <asciinema-player src="..."/> 直接対応。

set -euo pipefail

LANG_CODE="${1:-ja}"
shift || true

MEDIA_DIR="${MEDIA_DIR:-docs/media}"
mkdir -p "$MEDIA_DIR"

SCENARIOS=(
  "rad-quick-tour"
  "append-roundtrip"
  "code-review"
  "mcp-roundtrip"
  "openai-http"
  "vlm-describe"
  "consolidation-mirror"
  "resident-cognition"
  "multi-track"
  "deception-filter"
  "rad-omniscience"
  "image-algorithm-advisor"
)

ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    *) shift ;;
  esac
done

record_one() {
  local sid="$1"
  local out="$MEDIA_DIR/${sid}_${LANG_CODE}.cast"
  echo "[record] $sid → $out (lang=$LANG_CODE)"
  LLIVE_DEMO_LANG="$LANG_CODE" \
  LLIVE_RESIDENT_DURATION=6 \
  LLIVE_DEMO_SEED=42 \
  LLIVE_DEMO_NO_COLOR=0 \
    asciinema rec \
      --overwrite \
      --command "llive-demo --only $sid --lang $LANG_CODE" \
      "$out"
}

if [[ -n "$ONLY" ]]; then
  record_one "$ONLY"
else
  for sid in "${SCENARIOS[@]}"; do
    record_one "$sid"
  done
fi

echo "[done] casts saved to $MEDIA_DIR/"
echo "  embed example (Mintlify): <asciinema-player src=\"$MEDIA_DIR/resident-cognition_ja.cast\"/>"
echo "  embed example (README):   <a href=\"https://asciinema.org/a/...\">demo</a>"
