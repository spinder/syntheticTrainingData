#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Interactive promptfoo runner — select judge, then initial or re-run mode
# ---------------------------------------------------------------------------

TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)

# ---- Judge selection -------------------------------------------------------
echo ""
echo "Select a judge:"
echo "  1) automated"
echo "  2) human"
echo "  3) llm"
echo ""
read -rp "Judge [1-3]: " judge_choice

case "$judge_choice" in
  1) JUDGE="automated" ;;
  2) JUDGE="human" ;;
  3) JUDGE="llm" ;;
  *)
    echo "Invalid choice. Exiting."
    exit 1
    ;;
esac

CONFIG="${JUDGE}/promptfooconfig.yaml"
LOG_DIR="${JUDGE}/logs"
OUTPUT_FILE="${LOG_DIR}/${TIMESTAMP}-${JUDGE}-results.json"

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG"
  exit 1
fi

# ---- Mode selection --------------------------------------------------------
echo ""
echo "Select mode for judge: ${JUDGE}"
echo "  1) initial  — fresh eval with current config/prompts"
echo "  2) rerun    — re-eval with latest config/prompt updates (same judge)"
echo ""
read -rp "Mode [1-2]: " mode_choice

case "$mode_choice" in
  1) MODE="initial" ;;
  2) MODE="rerun" ;;
  *)
    echo "Invalid choice. Exiting."
    exit 1
    ;;
esac

# ---- Optional: filter by category ------------------------------------------
echo ""
read -rp "Filter pattern (leave blank for all tests): " FILTER

# ---- Run -------------------------------------------------------------------
mkdir -p "$LOG_DIR"

EVAL_CMD=(
  promptfoo eval
  --config "$CONFIG"
  --output "$OUTPUT_FILE"
)

if [[ -n "$FILTER" ]]; then
  EVAL_CMD+=(--filter-pattern "$FILTER")
fi

echo ""
echo "----------------------------------------"
echo "  Judge  : $JUDGE"
echo "  Mode   : $MODE"
echo "  Config : $CONFIG"
echo "  Output : $OUTPUT_FILE"
[[ -n "$FILTER" ]] && echo "  Filter : $FILTER"
echo "  Logs   : $LOG_DIR"
echo "----------------------------------------"
echo ""

export PROMPTFOO_LOG_DIR="$LOG_DIR"
"${EVAL_CMD[@]}"

echo ""
echo "Run complete. Results saved to: $OUTPUT_FILE"
echo ""
echo "Open UI:  promptfoo view $OUTPUT_FILE"
