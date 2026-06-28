#!/usr/bin/env bash
# AreAllSettingsDependenciesInPlace.sh
# Checks every env var, API key, Python package, and project file needed to run
# the synthetic data pipeline. Prints a clear readiness verdict with fix instructions.
#
# Usage (from project root):
#   bash AreAllSettingsDependenciesInPlace.sh
#   chmod +x AreAllSettingsDependenciesInPlace.sh && ./AreAllSettingsDependenciesInPlace.sh

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then   # only use colour when writing to a terminal
    RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "  ${RED}✗${RESET}  $*"; }
tip()  { echo -e "  ${CYAN}→${RESET}  $*"; }
hdr()  { echo -e "\n${BOLD}$*${RESET}"; echo "  $(printf '─%.0s' {1..66})"; }

# ── State tracking ────────────────────────────────────────────────────────────
ERRORS=0
WARNINGS=0
SUGGESTIONS=()

add_suggestion() { SUGGESTIONS+=("$1"); }
note_error()     { (( ERRORS++ )) || true; }
note_warning()   { (( WARNINGS++ )) || true; }

# ── Helpers ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mask_key() {
    # Show first 12 chars + "..." if the key is long enough
    local key="$1"
    local len=${#key}
    if [[ $len -le 12 ]]; then
        echo "${key}"
    else
        echo "${key:0:12}..."
    fi
}

provider_key_var() {
    # Return the env-var name that holds the API key for a given provider
    case "$1" in
        groq)     echo "GROQ_API_KEY" ;;
        claude)   echo "ANTHROPIC_API_KEY" ;;
        openai)   echo "OPENAI_API_KEY" ;;
        deepseek) echo "DEEPSEEK_API_KEY" ;;
        ollama)   echo "" ;;          # no key needed
        *)        echo "" ;;
    esac
}

provider_default_model() {
    case "$1" in
        groq)     echo "llama-3.1-8b-instant" ;;
        claude)   echo "claude-haiku-4-5-20251001" ;;
        openai)   echo "gpt-4o-mini" ;;
        deepseek) echo "deepseek-chat" ;;
        ollama)   echo "llama3.1" ;;
        *)        echo "unknown" ;;
    esac
}

VALID_PROVIDERS=("groq" "claude" "openai" "deepseek" "ollama")

is_valid_provider() {
    local p="$1"
    for v in "${VALID_PROVIDERS[@]}"; do [[ "$v" == "$p" ]] && return 0; done
    return 1
}

check_provider_key() {
    # $1=label (Generator|Judge)  $2=provider  $3=model (may be empty)
    local label="$1" provider="$2" model="${3:-}"
    local key_var default_model actual_model

    if ! is_valid_provider "$provider"; then
        fail "$label provider '${provider}' is not a recognised value."
        tip  "Valid values: ${VALID_PROVIDERS[*]}"
        note_error; return
    fi

    key_var="$(provider_key_var "$provider")"
    default_model="$(provider_default_model "$provider")"
    actual_model="${model:-$default_model}"

    if [[ "$provider" == "ollama" ]]; then
        ok  "$label provider : ollama  (model: ${actual_model})  — local inference, no API key needed"
        warn "Ollama requires the model to be pulled locally and enough RAM/VRAM."
        tip  "Verify: ollama list | grep ${actual_model}"
        note_warning
        return
    fi

    local key_val
    key_val="${!key_var:-}"   # indirect expansion

    if [[ -z "$key_val" ]]; then
        fail "$label provider : ${provider}  (model: ${actual_model})"
        fail "  ${key_var} is NOT SET"
        case "$provider" in
            groq)
                tip  "Get a free key at https://console.groq.com then:"
                tip  "  source .projectHistory/setLlmKeyValueGroq.sh"
                tip  "  — or —  export GROQ_API_KEY='gsk_...'"
                ;;
            openai)
                tip  "Get a key at https://platform.openai.com/api-keys then:"
                tip  "  source .projectHistory/setLlmKeyValueOpenAi.sh"
                tip  "  — or —  export OPENAI_API_KEY='sk-...'"
                ;;
            claude)
                tip  "Get a key at https://console.anthropic.com then:"
                tip  "  export ANTHROPIC_API_KEY='sk-ant-...'"
                ;;
            deepseek)
                tip  "Get a key at https://platform.deepseek.com then:"
                tip  "  export DEEPSEEK_API_KEY='sk-...'"
                ;;
        esac
        note_error
    else
        ok "$label provider : ${provider}  (model: ${actual_model})"
        ok "  ${key_var} = $(mask_key "$key_val")  [set]"
    fi
}

# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Pipeline Readiness Check — Home DIY Repair Synthetic Data      ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════════╝${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
hdr "1. LLM Environment Variables"

# Generator
GEN_PROVIDER="${LLM_PROVIDER:-}"
GEN_MODEL="${LLM_MODEL:-}"

if [[ -z "$GEN_PROVIDER" ]]; then
    fail "LLM_PROVIDER is NOT SET  (required — controls the data generator)"
    tip  "source .projectHistory/setLlmKeyValueGroq.sh     # recommended: groq (weak model)"
    tip  "— or —  export LLM_PROVIDER=groq"
    note_error
    GEN_PROVIDER="groq"   # assume groq for subsequent display even if unset
else
    ok   "LLM_PROVIDER     = ${GEN_PROVIDER}"
fi

if [[ -z "$GEN_MODEL" ]]; then
    warn "LLM_MODEL is not set — will use default: $(provider_default_model "$GEN_PROVIDER")"
    note_warning
else
    ok   "LLM_MODEL        = ${GEN_MODEL}"
fi

echo ""

# Judge
JUDGE_PROVIDER="${JUDGE_LLM_PROVIDER:-}"
JUDGE_MODEL="${JUDGE_LLM_MODEL:-}"
SPLIT_MODE=false

if [[ -z "$JUDGE_PROVIDER" ]]; then
    warn "JUDGE_LLM_PROVIDER is not set — judge will use the same provider as the generator"
    warn "  (This is fine for a single-provider run, but may be slow.)"
    tip  "To split: source .projectHistory/setJudgeProvider_openai.sh"
    tip  "  or run the one-shot recommended config:"
    tip  "  source .projectHistory/setProviders_recommended.sh"
    add_suggestion "Consider setting JUDGE_LLM_PROVIDER=openai for faster judging"
    note_warning
else
    SPLIT_MODE=true
    ok   "JUDGE_LLM_PROVIDER = ${JUDGE_PROVIDER}"
fi

if [[ -n "$JUDGE_PROVIDER" ]]; then
    if [[ -z "$JUDGE_MODEL" ]]; then
        warn "JUDGE_LLM_MODEL is not set — will use default: $(provider_default_model "$JUDGE_PROVIDER")"
        note_warning
    else
        ok   "JUDGE_LLM_MODEL  = ${JUDGE_MODEL}"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "2. API Keys & Provider Validation"

GEN_MODEL_EFF="${GEN_MODEL:-$(provider_default_model "$GEN_PROVIDER")}"
check_provider_key "Generator" "$GEN_PROVIDER" "$GEN_MODEL_EFF"

echo ""

if $SPLIT_MODE; then
    JUDGE_MODEL_EFF="${JUDGE_MODEL:-$(provider_default_model "$JUDGE_PROVIDER")}"
    check_provider_key "Judge    " "$JUDGE_PROVIDER" "$JUDGE_MODEL_EFF"
else
    ok "Judge     : [same as generator — no separate key needed]"
fi

# HuggingFace (optional)
echo ""
HF_KEY="${HF_API_KEY:-}"
if [[ -z "$HF_KEY" ]]; then
    warn "HF_API_KEY is not set  (optional — only needed for validate_hf_dataset.py)"
    tip  "export HF_API_KEY='hf_...'  to enable HuggingFace benchmark validation"
    add_suggestion "Set HF_API_KEY if you want to run validate_hf_dataset.py"
else
    ok   "HF_API_KEY       = $(mask_key "$HF_KEY")  [set — HuggingFace validation available]"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "3. Python Dependencies"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" &>/dev/null; then
    fail "python3 not found in PATH"
    tip  "Install Python 3.10+ and ensure it is on your PATH"
    note_error
else
    PY_VER=$("$PYTHON_BIN" --version 2>&1)
    ok   "$PY_VER  at $(command -v "$PYTHON_BIN")"
fi

PACKAGES=(
    "instructor:instructor"
    "anthropic:anthropic"
    "openai:openai"
    "groq:groq"
    "pydantic:pydantic"
    "jsonschema:jsonschema"
    "matplotlib:matplotlib"
    "numpy:numpy"
    "pandas:pandas"
    "pyarrow:pyarrow"
    "datasets:datasets"
    "huggingface_hub:huggingface_hub"
    "yaml:pyyaml"
)

MISSING_PKGS=()
for entry in "${PACKAGES[@]}"; do
    import_name="${entry%%:*}"
    install_name="${entry##*:}"
    if "$PYTHON_BIN" -c "import ${import_name}" 2>/dev/null; then
        ok   "${import_name}"
    else
        fail "${import_name}  (pip package: ${install_name})"
        MISSING_PKGS+=("$install_name")
        note_error
    fi
done

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    echo ""
    tip  "Install all missing packages:"
    tip  "  pip install ${MISSING_PKGS[*]}"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "4. Required Project Files"

REQUIRED_FILES=(
    "run_pipeline.py:Main orchestrator"
    "generate.py:Step 1 generator"
    "quality_gate.py:Step 2 quality gate"
    "batch_judge.py:Step 4 LLM judge runner"
    "human_batch.py:Step 3 human labeler"
    "export_labels.py:Step 5b label export"
    "visualize.py:Chart generator"
    "prompts/iter1_weak.txt:Baseline (weak) generation prompt"
    "schema/model.py:Pydantic schema"
    "llm/providers/llm_judge_provider.py:Judge provider"
)

for entry in "${REQUIRED_FILES[@]}"; do
    fpath="${entry%%:*}"
    desc="${entry##*:}"
    if [[ -f "${SCRIPT_DIR}/${fpath}" ]]; then
        ok   "${fpath}  — ${desc}"
    else
        fail "${fpath}  — ${desc}  [FILE MISSING]"
        note_error
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
hdr "5. Setup Scripts"

SETUP_SCRIPTS=(
    ".projectHistory/setLlmKeyValueGroq.sh:Set GROQ_API_KEY + generator provider"
    ".projectHistory/setLlmKeyValueOpenAi.sh:Set OPENAI_API_KEY + provider"
    ".projectHistory/setJudgeProvider_openai.sh:Set JUDGE_LLM_PROVIDER=openai (separate judge)"
    ".projectHistory/setProviders_recommended.sh:One-shot recommended split-provider config"
)

for entry in "${SETUP_SCRIPTS[@]}"; do
    fpath="${entry%%:*}"
    desc="${entry##*:}"
    if [[ -f "${SCRIPT_DIR}/${fpath}" ]]; then
        ok   "${fpath}  — ${desc}"
    else
        warn "${fpath}  — ${desc}  [not found]"
        note_warning
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
hdr "6. Pipeline State"

STATE_FILE="${SCRIPT_DIR}/.pipeline_state.json"
if [[ -f "$STATE_FILE" ]]; then
    # Parse with python3 to avoid jq dependency
    STATE_INFO=$("$PYTHON_BIN" - <<'EOF'
import json, sys
try:
    d = json.load(open(".pipeline_state.json"))
    completed = d.get("completed", [])
    variant   = d.get("variant", "unknown")
    files     = d.get("files", {})
    print(f"  variant  : {variant}")
    print(f"  completed: {', '.join(completed) if completed else '(none)'}")
    gated = files.get("gated_jsonl","")
    print(f"  gated    : {gated if gated else '(not yet generated)'}")
    llm = files.get("llm_results","")
    print(f"  llm      : {llm if llm else '(not yet judged)'}")
    human = files.get("human_results","")
    print(f"  human    : {human if human else '(not yet labeled)'}")
except Exception as e:
    print(f"  (could not parse state file: {e})")
EOF
    2>/dev/null || echo "  (python parse failed)")
    warn ".pipeline_state.json exists — a previous run was in progress:"
    while IFS= read -r line; do echo "    $line"; done <<< "$STATE_INFO"
    echo ""
    tip  "To RESUME the previous run:"
    tip  "    python3 run_pipeline.py --resume --auto-correct"
    tip  "To RESTART from scratch:"
    tip  "    python3 run_pipeline.py --reset && python3 run_pipeline.py --auto-correct"
else
    ok   "No .pipeline_state.json — pipeline will start fresh from Step 1"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "7. Readiness Verdict"

GEN_KEY_VAR="$(provider_key_var "$GEN_PROVIDER")"
GEN_KEY_OK=false
if [[ "$GEN_PROVIDER" == "ollama" ]] || { [[ -n "$GEN_KEY_VAR" ]] && [[ -n "${!GEN_KEY_VAR:-}" ]]; }; then
    GEN_KEY_OK=true
fi

JUDGE_KEY_OK=false
if $SPLIT_MODE; then
    JUDGE_KEY_VAR="$(provider_key_var "$JUDGE_PROVIDER")"
    if [[ "$JUDGE_PROVIDER" == "ollama" ]] || { [[ -n "$JUDGE_KEY_VAR" ]] && [[ -n "${!JUDGE_KEY_VAR:-}" ]]; }; then
        JUDGE_KEY_OK=true
    fi
else
    JUDGE_KEY_OK=true   # same as generator — already checked
fi

LLM_PROVIDER_SET=$([[ -n "$GEN_PROVIDER" && "$GEN_PROVIDER" != "" ]] && echo true || echo false)

echo ""
if [[ $ERRORS -eq 0 ]] && $GEN_KEY_OK && $JUDGE_KEY_OK && $LLM_PROVIDER_SET; then
    if $SPLIT_MODE; then
        echo -e "  ${GREEN}${BOLD}✓ READY — SPLIT-PROVIDER MODE${RESET}"
        echo ""
        echo -e "  ${GREEN}Generator : ${GEN_PROVIDER} / ${GEN_MODEL_EFF}${RESET}"
        echo -e "  ${GREEN}            Weak model → genuine baseline failures (target ≥ 15% fail rate)${RESET}"
        echo -e "  ${GREEN}Judge     : ${JUDGE_PROVIDER} / ${JUDGE_MODEL_EFF}${RESET}"
        echo -e "  ${GREEN}            Stronger model → accurate, fast judgments${RESET}"
        echo ""
        echo -e "  ${BOLD}Run now:${RESET}"
        echo "    python3 run_pipeline.py --auto-correct"
        echo "    # -- or via the menu --"
        echo "    ./.projectHistory/promptTools.sh  →  f  →  1"
    else
        echo -e "  ${YELLOW}${BOLD}⚠ READY — SINGLE-PROVIDER MODE${RESET}"
        echo ""
        echo -e "  ${YELLOW}Generator + Judge : ${GEN_PROVIDER} / ${GEN_MODEL_EFF}${RESET}"
        echo ""
        echo -e "  ${YELLOW}This works, but consider the trade-offs:${RESET}"
        echo "    • ${GEN_PROVIDER} will be used for BOTH generation and 360 judge calls in Step 4"
        if [[ "$GEN_PROVIDER" == "groq" ]]; then
            echo "    • Groq free tier is rate-limited → Step 4 will take ~22 min instead of ~5 min"
            echo "    • Generation quality is appropriately weak for a real baseline ✓"
        elif [[ "$GEN_PROVIDER" == "openai" || "$GEN_PROVIDER" == "claude" ]]; then
            echo "    • WARNING: A strong model may follow even a weak prompt well enough"
            echo "      to produce < 15% failures — making the ≥ 80% improvement target very hard"
            echo "    • Consider: keep this provider as judge, use groq for generation"
        fi
        echo ""
        echo -e "  ${BOLD}To split providers (recommended):${RESET}"
        echo "    source .projectHistory/setProviders_recommended.sh"
        echo "    bash AreAllSettingsDependenciesInPlace.sh   # re-check"
        echo ""
        echo -e "  ${BOLD}Run anyway (single provider):${RESET}"
        echo "    python3 run_pipeline.py --auto-correct"
    fi
else
    echo -e "  ${RED}${BOLD}✗ NOT READY — ${ERRORS} error(s) must be fixed before running${RESET}"
    echo ""

    if ! $LLM_PROVIDER_SET; then
        echo -e "  ${RED}Missing: LLM_PROVIDER${RESET}"
        tip "source .projectHistory/setLlmKeyValueGroq.sh"
    fi

    if ! $GEN_KEY_OK && [[ -n "$GEN_KEY_VAR" ]]; then
        echo -e "  ${RED}Missing: ${GEN_KEY_VAR} (for generator provider '${GEN_PROVIDER}')${RESET}"
        case "$GEN_PROVIDER" in
            groq)
                tip "source .projectHistory/setLlmKeyValueGroq.sh"
                tip "  — or —  export GROQ_API_KEY='gsk_...'"
                ;;
            openai)
                tip "source .projectHistory/setLlmKeyValueOpenAi.sh"
                tip "  — or —  export OPENAI_API_KEY='sk-...'"
                ;;
            claude)
                tip "export ANTHROPIC_API_KEY='sk-ant-...'"
                ;;
        esac
    fi

    if $SPLIT_MODE && ! $JUDGE_KEY_OK && [[ -n "${JUDGE_KEY_VAR:-}" ]]; then
        echo -e "  ${RED}Missing: ${JUDGE_KEY_VAR} (for judge provider '${JUDGE_PROVIDER}')${RESET}"
        case "$JUDGE_PROVIDER" in
            openai)
                tip "source .projectHistory/setLlmKeyValueOpenAi.sh"
                tip "  — or —  export OPENAI_API_KEY='sk-...'"
                ;;
            groq)
                tip "source .projectHistory/setLlmKeyValueGroq.sh"
                ;;
        esac
    fi

    if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
        echo ""
        echo -e "  ${RED}Missing Python packages: ${MISSING_PKGS[*]}${RESET}"
        tip "pip install ${MISSING_PKGS[*]}"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if [[ ${#SUGGESTIONS[@]} -gt 0 ]]; then
    hdr "8. Additional Suggestions"
    for s in "${SUGGESTIONS[@]}"; do
        tip "$s"
    done
fi

echo ""
echo -e "${BOLD}  Summary: ${ERRORS} error(s)  ${WARNINGS} warning(s)${RESET}"
echo ""

# Exit with non-zero if there are blocking errors (useful for CI / scripting)
[[ $ERRORS -eq 0 ]]
