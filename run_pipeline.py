#!/usr/bin/env python3
"""
run_pipeline.py — Guided orchestrator for the Home DIY Repair pipeline.

Runs all automatable steps automatically and pauses at interactive steps
with exact copy-paste commands (filenames filled in from state) and
explicit .projectHistory/promptTools.sh navigation instructions.

State is saved to .pipeline_state.json after every step so the session
can be resumed at any point.

━━━ ESTIMATED TIME ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Step 1   Generate 60 items (Groq)          ~8 min
  Step 2   Quality gate                      <1 min
  Step 4   LLM batch judge (360 tests)       ~8 min
  Step 5a  Auto charts                       <1 min
  ─────────────────────────────────────────────────────────────────
  Step 3   Human labeling ×20 items         ~40 min  ← you do this
  Step 5b  Export labels + agreement chart   <1 min
  ─────────────────────────────────────────────────────────────────
  Step 6A  Judge calibration (1–2 loops)    ~25 min/loop
  Step 6B  Generator correction             ~10 min/loop (--auto-correct)
                                            ~40 min/loop (manual)
  ─────────────────────────────────────────────────────────────────
  TOTAL (--auto-correct)  ~2–3 hours
  TOTAL (manual)          ~3–5 hours

━━━ USAGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # New baseline run (Groq, weak prompt):
  python3 run_pipeline.py

  # With LLM-assisted Phase B prompt correction:
  python3 run_pipeline.py --auto-correct

  # Specify prompt file and item count:
  python3 run_pipeline.py --prompt-file prompts/iter1_weak.txt --per-category 12

  # Resume from saved state (e.g. after human labeling):
  python3 run_pipeline.py --resume

  # Jump to a specific step (skips all earlier steps):
  python3 run_pipeline.py --resume-from 6B

  # Clear state and start fresh:
  python3 run_pipeline.py --reset
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT       = Path(__file__).parent.resolve()
STATE_FILE = ROOT / ".pipeline_state.json"

PROVIDER_DEFAULTS = {
    "groq":     {"model": "llama-3.1-8b-instant", "key_var": "GROQ_API_KEY"},
    "claude":   {"model": "claude-sonnet-4-6",     "key_var": "ANTHROPIC_API_KEY"},
    "openai":   {"model": "gpt-4o",                "key_var": "OPENAI_API_KEY"},
    "deepseek": {"model": "deepseek-chat",          "key_var": "DEEPSEEK_API_KEY"},
}

STEP_ORDER = ["1", "2", "4", "5a", "3", "5b", "6A", "6B", "final"]

DIM_TO_Q = {
    "answer_completeness":   "q1",
    "safety_specificity":    "q2",
    "tool_realism":          "q3",
    "scope_appropriateness": "q4",
    "context_clarity":       "q5",
    "tip_usefulness":        "q6",
}

DIM_NUM = {d: i + 1 for i, d in enumerate(DIM_TO_Q)}

DIM_DEFINITIONS = {
    "answer_completeness": (
        "D1: The answer must contain enough detail for a homeowner to complete the repair "
        "end-to-end — covering tools, concrete numbered steps, a safety warning, and at least "
        "one useful tip. Answers that stop short or omit key stages fail."
    ),
    "safety_specificity": (
        "D2: safety_info must name the SPECIFIC hazard of this repair (e.g., 'electric shock "
        "from live wires', 'scalding water under pressure') AND the SPECIFIC precaution to take "
        "(e.g., 'turn off the circuit breaker and verify with a voltage tester'). "
        "Generic phrases like 'be careful', 'use caution', or 'stay safe' always fail."
    ),
    "tool_realism": (
        "D3: Every tool listed in tools_required must be something a typical homeowner already "
        "owns or can buy at a general hardware store for under $50. No professional-grade, "
        "trade-only, or specialty equipment. A pipe wrench or voltage tester passes; "
        "a commercial pipe threader or oscilloscope fails."
    ),
    "scope_appropriateness": (
        "D4: The repair must be within realistic DIY capability for a careful homeowner. "
        "If professional help is genuinely required (gas lines, main electrical panel, "
        "structural work), the answer must say so clearly rather than providing amateur "
        "instructions that could cause injury."
    ),
    "context_clarity": (
        "D5: The question and answer must contain enough context for the reader to understand "
        "the specific problem, and the answer must directly address the equipment_problem field "
        "— not a generic version of the repair category."
    ),
    "tip_usefulness": (
        "D6: Each tip must provide non-obvious, task-specific advice that goes beyond the steps. "
        "Tips that restate a step ('make sure to tighten the bolt'), offer generic praise "
        "('good job!'), or give obvious advice ('be careful') always fail."
    ),
}

SHORT_TO_FULL = {
    "appliance":    "appliance_repair",
    "general_home": "general_home_repair",
    "plumbing":     "plumbing_repair",
    "electrical":   "electrical_repair",
    "hvac":         "hvac_maintenance",
}

NOTES_FILE = ROOT / "human" / "logs" / ".session_notes.txt"


# ── Core helpers ───────────────────────────────────────────────────────────────

def _hr(c="━", w=72): print(c * w)

def _header(title: str, badge: str = "AUTO") -> None:
    _hr()
    print(f"  [{badge}]  {title}")
    _hr()

def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": [], "files": {}}

def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))

def _newest(pattern: str, exclude: str = "") -> Path | None:
    hits = [p for p in ROOT.glob(pattern)
            if not exclude or exclude not in p.name]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None

def _elapsed(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s" if m else f"{sec}s"

def _run(cmd: list, ok_codes: tuple = (0,), cwd: Path | None = None) -> int:
    cmd_s = " ".join(str(c) for c in cmd)
    print(f"\n  $ {cmd_s}")
    t0 = time.time()
    r  = subprocess.run([str(c) for c in cmd], cwd=cwd or ROOT)
    t  = time.time() - t0
    marker = "✓" if r.returncode in ok_codes else "✗"
    print(f"  {marker} Exit {r.returncode}  ({_elapsed(t)})")
    return r.returncode

def _pause(title: str, body: str) -> None:
    print(f"\n{'━'*72}")
    print(f"  ⏸  {title}")
    print(f"{'━'*72}")
    print(body)
    input("\n  Press Enter when done → ")
    print()

def _make_judge_env(args) -> dict:
    """Return an env dict with JUDGE_LLM_PROVIDER/MODEL injected for subprocess calls."""
    env = os.environ.copy()
    # Explicit --judge-provider flag takes precedence, then JUDGE_LLM_PROVIDER env var,
    # then fall back to the generation provider so behaviour is always deterministic.
    jp = getattr(args, "judge_provider", "") or os.environ.get("JUDGE_LLM_PROVIDER", "")
    jm = getattr(args, "judge_model", "")    or os.environ.get("JUDGE_LLM_MODEL", "")
    if jp:
        env["JUDGE_LLM_PROVIDER"] = jp
        key_var = PROVIDER_DEFAULTS.get(jp, {}).get("key_var", "")
        if key_var and not env.get(key_var):
            sys.exit(f"ERROR: {key_var} is not set (required for judge provider '{jp}')")
    if jm:
        env["JUDGE_LLM_MODEL"] = jm
    return env


def _run_judge(gated_path: str, args, extra_flags: list | None = None) -> int:
    """Run batch_judge.py with the correct judge env injected. Returns exit code."""
    env  = _make_judge_env(args)
    jp   = env.get("JUDGE_LLM_PROVIDER") or getattr(args, "provider", "groq")
    jm   = env.get("JUDGE_LLM_MODEL") or PROVIDER_DEFAULTS.get(jp, {}).get("model", "default")
    print(f"  Judge provider : {jp}  ({jm})")
    cmd  = [sys.executable, str(ROOT / "batch_judge.py"), str(ROOT / gated_path)]
    if extra_flags:
        cmd += extra_flags
    print(f"\n  $ {' '.join(str(c) for c in cmd)}")
    t0 = time.time()
    r  = subprocess.run([str(c) for c in cmd], cwd=ROOT, env=env)
    print(f"  {'✓' if r.returncode in (0, 1) else '✗'} Exit {r.returncode}  ({_elapsed(time.time() - t0)})")
    return r.returncode


def _check_agreement(path: Path) -> tuple[bool, dict]:
    if not path.exists():
        return False, {}
    data = json.loads(path.read_text())
    return data.get("calibrated", False), data.get("dimensions", {})


# ── Auto-correct helpers ───────────────────────────────────────────────────────

def _worst_segment(llm_results_path: Path) -> tuple[str, str, float]:
    """Return (worst_raw_cat, worst_dim, fail_rate) from LLM batch results."""
    data = json.loads(llm_results_path.read_text())
    rows = data["results"]["results"]

    from collections import defaultdict
    cell: dict[tuple[str, str], list[bool]] = defaultdict(list)

    for row in rows:
        desc = (row.get("testCase") or {}).get("description", "")
        m = re.match(r"item_\d+_(\w+)\s*\|\s*D\d+\s+(\w+)", desc)
        if not m:
            continue
        raw_cat, dim = m.group(1), m.group(2)
        output = (row.get("response") or {}).get("output", "").strip().lower()
        if output in ("pass", "fail"):
            cell[(raw_cat, dim)].append(output == "pass")

    worst_cat, worst_dim, worst_fail = "unknown", "unknown", 0.0
    for (cat, dim), verdicts in cell.items():
        rate = sum(1 for v in verdicts if not v) / len(verdicts)
        if rate > worst_fail:
            worst_fail, worst_cat, worst_dim = rate, cat, dim

    return worst_cat, worst_dim, worst_fail


def _collect_failure_notes(dim_key: str, dim_num: int) -> str:
    """Collect human failure notes for a specific dimension from git log + session file."""
    notes: list[str] = []
    dim_tag = f"D{dim_num}"

    # From git log commit messages
    try:
        out = subprocess.run(
            ["git", "log", "--format=%B"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        ).stdout
        for line in out.splitlines():
            if dim_tag in line and "FAIL" in line:
                notes.append(line.strip())
    except Exception:
        pass

    # From current session notes file
    if NOTES_FILE.exists():
        for line in NOTES_FILE.read_text().splitlines():
            if dim_tag in line and "FAIL" in line:
                notes.append(line.strip())

    # Deduplicate and limit
    seen, unique = set(), []
    for n in notes:
        if n not in seen:
            seen.add(n)
            unique.append(n)

    return "\n".join(unique[-20:])


def _call_llm(prompt_text: str) -> str:
    """Call the configured LLM provider and return the text response.
    Uses JUDGE_LLM_PROVIDER/JUDGE_LLM_MODEL if set, else falls back to LLM_PROVIDER."""
    provider = (os.getenv("JUDGE_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "groq")).lower()
    model    = (os.getenv("JUDGE_LLM_MODEL") or os.getenv("LLM_MODEL")
                or PROVIDER_DEFAULTS.get(provider, {}).get("model", ""))

    if provider == "groq":
        try:
            from groq import Groq
        except ImportError:
            sys.exit("ERROR: groq package not installed — pip install groq")
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        resp = client.chat.completions.create(
            model=model or "llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.3, max_tokens=600,
        )
        return resp.choices[0].message.content.strip()

    elif provider == "claude":
        try:
            import anthropic
        except ImportError:
            sys.exit("ERROR: anthropic package not installed — pip install anthropic")
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=model or "claude-sonnet-4-6",
            max_tokens=600, temperature=0.3,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return resp.content[0].text.strip()

    elif provider == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            sys.exit("ERROR: openai package not installed — pip install openai")
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.3, max_tokens=600,
        )
        return resp.choices[0].message.content.strip()

    else:
        sys.exit(f"ERROR: unsupported provider '{provider}' for --auto-correct. "
                 "Set LLM_PROVIDER=groq|claude|openai")


def _auto_correct_prompt(state: dict, next_variant: str) -> Path | None:
    """
    Analyse the latest LLM results, call an LLM to suggest a targeted
    prompt improvement, get user approval, and write the new prompt file.
    Returns the path to the new file, or None if the user chose to skip.
    """
    llm_results_rel = state["files"].get("llm_results")
    if not llm_results_rel:
        print("  WARNING: no LLM results in state — cannot auto-correct")
        return None

    llm_results_path = ROOT / llm_results_rel
    if not llm_results_path.exists():
        print(f"  WARNING: {llm_results_path} not found")
        return None

    print("\n  Analysing results to identify worst segment × dimension …")
    worst_cat, worst_dim, fail_rate = _worst_segment(llm_results_path)
    dim_num = DIM_NUM.get(worst_dim, "?")
    full_cat = SHORT_TO_FULL.get(worst_cat, worst_cat)

    print(f"  Worst segment  : {worst_cat}  ×  D{dim_num} {worst_dim}")
    print(f"  Fail rate      : {fail_rate:.0%}")

    # Current prompt
    variant = state.get("variant", "iter1_weak")
    current_prompt_path = ROOT / "prompts" / f"{variant}.txt"
    if not current_prompt_path.exists():
        print(f"  WARNING: prompt file not found: {current_prompt_path}")
        return None
    current_prompt = current_prompt_path.read_text()

    # Failure notes for this dimension
    notes = _collect_failure_notes(worst_dim, dim_num)
    notes_section = notes if notes else "(No human failure notes yet — use the dimension definition above.)"

    dim_def = DIM_DEFINITIONS.get(worst_dim, f"D{dim_num}: {worst_dim}")

    synthesis_prompt = f"""You are a prompt engineer improving a Home DIY Repair Q&A data generator.

## Current generation prompt
{current_prompt}

## Quality problem to fix
- Category failing : {full_cat.replace("_", " ")}
- Dimension failing: D{dim_num} {worst_dim} — fail rate: {fail_rate:.0%}
- Dimension rule   : {dim_def}

## What human reviewers flagged as failures
{notes_section}

## Your task
Write a SHORT, TARGETED addition (2–5 sentences) to INSERT into the generation prompt
that specifically fixes the failing dimension for the {full_cat.replace("_", " ")} category.

Rules:
- Be concrete: tell the LLM exactly what a PASSING response looks like
- One brief inline example is fine if it clarifies the rule
- Do NOT rewrite the whole prompt; do NOT add rules for other dimensions
- Output ONLY the addition text — no headers, no explanation, no preamble."""

    print("\n  Calling LLM to generate prompt improvement …")
    try:
        suggestion = _call_llm(synthesis_prompt)
    except Exception as exc:
        print(f"  ERROR calling LLM: {exc}")
        print("  Falling back to manual correction mode.")
        return None

    # Show suggestion and get approval
    print(f"\n{'━'*72}")
    print(f"  Suggested addition for D{dim_num} {worst_dim}  [{worst_cat}]:")
    print(f"{'─'*72}")
    print()
    for line in suggestion.splitlines():
        print(f"  {line}")
    print()
    print(f"{'━'*72}")

    while True:
        choice = input("  [a]ccept  /  [e]dit  /  [s]kip to manual: ").strip().lower()
        if choice in ("a", "accept", ""):
            addition = suggestion
            break
        elif choice in ("e", "edit"):
            print("  Paste your edited version. Enter a blank line when done:")
            lines = []
            while True:
                ln = input()
                if ln == "":
                    break
                lines.append(ln)
            addition = "\n".join(lines)
            break
        elif choice in ("s", "skip"):
            print("  Skipping auto-correct — reverting to manual Phase B.")
            return None

    # Write the corrected prompt file
    corrected_path = ROOT / "prompts" / f"{next_variant}.txt"
    header_comment = (
        f"\n\n# ── Auto-correct addition (targeting D{dim_num} {worst_dim} / {worst_cat}) ──\n"
    )
    corrected_path.write_text(current_prompt.rstrip() + header_comment + addition + "\n")

    print(f"\n  ✓ Written  : {corrected_path}")
    print(f"  Review it  : open prompts/{next_variant}.txt and edit if needed")
    input("  Press Enter when satisfied with the prompt → ")
    return corrected_path


# ── Pipeline steps ─────────────────────────────────────────────────────────────

def step1_generate(state: dict, args) -> None:
    _header("Step 1 — Generate", badge="AUTO")
    prompt_file = Path(args.prompt_file)
    if not prompt_file.exists():
        sys.exit(f"ERROR: prompt file not found: {prompt_file}")
    variant = prompt_file.stem
    cmd = [sys.executable, ROOT / "generate.py",
           "--prompt-file", str(prompt_file),
           "--per-category", str(args.per_category),
           "--provider", args.provider]
    if args.model:
        cmd += ["--model", args.model]

    rc = _run(cmd)
    if rc != 0:
        sys.exit(rc)

    latest = _newest(f"generated_data/{variant}_*.jsonl", exclude="_gated")
    if latest:
        state["files"]["jsonl"] = str(latest.relative_to(ROOT))
        state["variant"]        = variant
        state["files"].setdefault("baseline_jsonl", str(latest.relative_to(ROOT)))
        print(f"  Output   : {latest}")
    else:
        print("  WARNING: could not auto-detect output JSONL")


def step2_gate(state: dict, args) -> None:
    _header("Step 2 — Quality Gate", badge="AUTO")
    jsonl = state["files"].get("jsonl")
    if not jsonl:
        sys.exit("ERROR: no JSONL in state — run Step 1 first")

    rc = _run([sys.executable, ROOT / "quality_gate.py", ROOT / jsonl], ok_codes=(0, 1))

    gated  = Path(str(ROOT / jsonl).replace(".jsonl", "_gated.jsonl"))
    report = Path(str(ROOT / jsonl).replace(".jsonl", "_gate_report.json"))
    if gated.exists():
        state["files"]["gated_jsonl"] = str(gated.relative_to(ROOT))
        state["files"]["gate_report"] = str(report.relative_to(ROOT))
        print(f"  Gated    : {gated}")
    if rc == 1:
        print("\n  ⚠  Distribution check failed — fix prompt weighting and re-run Step 1.")
        cont = input("  Continue anyway? [y/N]: ").strip().lower()
        if cont != "y":
            sys.exit(1)


def step4_llm_judge(state: dict, args) -> None:
    _header("Step 4 — LLM Batch Judge", badge="AUTO")
    gated = state["files"].get("gated_jsonl")
    if not gated:
        sys.exit("ERROR: no gated JSONL in state — run Step 2 first")

    _run_judge(gated, args)

    latest = _newest("llm/logs/*-batch-*-results.json")
    if latest:
        state["files"]["llm_results"] = str(latest.relative_to(ROOT))
        state["files"].setdefault("baseline_llm_results", str(latest.relative_to(ROOT)))
        print(f"  Results  : {latest}")


def step5a_charts(state: dict, args) -> None:
    _header("Step 5a — Auto Charts (LLM judge)", badge="AUTO")
    llm = state["files"].get("llm_results")
    if not llm:
        print("  WARNING: no LLM results in state — skipping")
        return
    variant   = state.get("variant", "run")
    chart_dir = ROOT / "charts" / f"{variant[:28]}_auto"
    chart_dir.mkdir(parents=True, exist_ok=True)
    state["files"]["auto_chart_dir"] = str(chart_dir.relative_to(ROOT))
    for chart in ("category_distribution", "pass_rate", "category_quality"):
        _run([sys.executable, ROOT / "visualize.py",
              ROOT / llm, "--chart", chart, "--output-dir", str(chart_dir)])
    print(f"\n  Charts   : {chart_dir}/")


def step3_human_label(state: dict, args) -> None:
    _header("Step 3 — Human Labeling", badge="PAUSE")
    gated   = state["files"].get("gated_jsonl", "generated_data/<gated>.jsonl")
    count   = args.human_count
    variant = state.get("variant", "")

    body = f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  Run this command in your OTHER terminal window:                │
  │                                                                 │
  │    python3 human_batch.py \\                                     │
  │        {gated:<51} \\│
  │        --count {count:<53}│
  │                                                                 │
  │  Controls:  [p] pass   [f] fail + one-line reason   [s] skip   │
  │  Items:     {count} items × 6 dimensions = {count * 6} prompts total        │
  │  Est. time: ~{count * 2} minutes                                        │
  │                                                                 │
  │  When done:                                                     │
  │    1. Accept the offered git commit to preserve failure notes.  │
  │    2. Note the output file path shown at the end.               │
  │    3. Press Enter here to continue.                             │
  └─────────────────────────────────────────────────────────────────┘"""
    _pause("Human Labeling  (est. ~40 min)", body)

    latest = _newest("human/logs/*-humanbatch-*-results.json")
    if latest:
        state["files"]["human_results"] = str(latest.relative_to(ROOT))
        print(f"  Detected : {latest}")
    else:
        path = input("  Could not auto-detect. Paste the path: ").strip()
        if path:
            state["files"]["human_results"] = path


def step5b_export(state: dict, args) -> None:
    _header("Step 5b — Export Labels + Agreement Chart", badge="AUTO")
    human = state["files"].get("human_results")
    llm   = state["files"].get("llm_results")
    if not human or not llm:
        sys.exit("ERROR: missing human or LLM results in state")

    variant  = state.get("variant", "run")
    pb_iter  = state.get("phase_b_iter", 1)
    out_stem = ROOT / "analysis" / f"{variant[:28]}_iter{pb_iter}"
    (ROOT / "analysis").mkdir(exist_ok=True)

    _run([sys.executable, ROOT / "export_labels.py",
          "--human", ROOT / human, "--llm", ROOT / llm, "--out", str(out_stem)])

    agree_path = Path(f"{out_stem}_agreement.json")
    if agree_path.exists():
        state["files"]["agreement"] = str(agree_path.relative_to(ROOT))
        calibrated, rates = _check_agreement(agree_path)
        state["phase_a_calibrated"] = calibrated

    chart_dir = ROOT / "charts" / f"{variant[:28]}_auto"
    chart_dir.mkdir(parents=True, exist_ok=True)
    _run([sys.executable, ROOT / "visualize.py",
          ROOT / human, ROOT / llm,
          "--chart", "human_llm_agreement", "--output-dir", str(chart_dir)])
    print(f"\n  Review   : {chart_dir}/human_llm_agreement.png")
    print(f"  Bars < 80% = judge miscalibrated → must fix before Phase B")


def step6a_calibration(state: dict, args) -> None:
    agree_file = ROOT / state["files"].get("agreement", "analysis/labels_agreement.json")
    calibrated, rates = _check_agreement(agree_file)

    if calibrated:
        _header("Step 6A — Judge already calibrated ✓  (all dims ≥ 80%)", badge="SKIP")
        print("  Skipping Phase A — proceeding to Phase B.\n")
        state["phase_a_calibrated"] = True
        return

    _header("Step 6A — Judge Calibration", badge="PAUSE")
    loop = 0

    while not calibrated:
        loop += 1
        print(f"\n  Phase A loop {loop} — current agreement:")
        worst_dim, worst_rate = None, 1.0
        for dim in DIM_TO_Q:
            rate = rates.get(dim)
            if rate is None:
                continue
            ok = "✓" if rate >= 0.80 else "✗"
            print(f"    {ok}  {dim:<28}  {rate:.0%}")
            if rate < worst_rate:
                worst_rate, worst_dim = rate, dim

        q_file = DIM_TO_Q.get(worst_dim, "q?")

        body = f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  Worst dimension : {worst_dim:<20}  ({worst_rate:.0%} agreement)   │
  │  Rubric files    : human/questions/{q_file}.txt                      │
  │                    llm/questions/{q_file}.txt                        │
  │                                                                 │
  │  1. Generate a rubric draft:                                    │
  │       ./.projectHistory/promptTools.sh                         │
  │       → Select:  e   (Generate rubric draft from failure notes) │
  │       Draft saved to: .projectHistory/rubric_draft_<ts>.md     │
  │                                                                 │
  │  2. Review and edit the draft:                                  │
  │       Tighten '{worst_dim}' criteria:      │
  │         • Add 1–2 concrete PASS examples                       │
  │         • Add 1–2 concrete FAIL examples                       │
  │         • Remove or clarify any ambiguous wording              │
  │                                                                 │
  │  3. Deploy the improved rubric:                                 │
  │       cp <approved section> → human/questions/{q_file}.txt          │
  │       cp same text          → llm/questions/{q_file}.txt            │
  │                                                                 │
  │  4. Press Enter — pipeline re-runs LLM judge and rechecks.    │
  └─────────────────────────────────────────────────────────────────┘"""
        _pause(f"Phase A loop {loop} — fix '{worst_dim}' rubric", body)

        # Re-run LLM judge on same gated JSONL (uses same judge provider as Step 4)
        gated = state["files"].get("gated_jsonl")
        print("  Re-running LLM judge on same gated JSONL …")
        _run_judge(gated, args)
        latest_llm = _newest("llm/logs/*-batch-*-results.json")
        if latest_llm:
            state["files"]["llm_results"] = str(latest_llm.relative_to(ROOT))

        variant  = state.get("variant", "run")
        out_stem = ROOT / "analysis" / f"{variant[:28]}_6A_loop{loop}"
        (ROOT / "analysis").mkdir(exist_ok=True)
        _run([sys.executable, ROOT / "export_labels.py",
              "--human", ROOT / state["files"]["human_results"],
              "--llm",   ROOT / state["files"]["llm_results"],
              "--out",   str(out_stem)])
        agree_file = Path(f"{out_stem}_agreement.json")
        if agree_file.exists():
            state["files"]["agreement"] = str(agree_file.relative_to(ROOT))
        calibrated, rates = _check_agreement(agree_file)
        state["phase_a_calibrated"] = calibrated
        _save(state)

        status = "✓ All dims ≥ 80% — Phase A complete!" if calibrated else "✗ Still miscalibrated — looping again …"
        print(f"\n  {status}")


def step6b_correction(state: dict, args) -> None:
    _header("Step 6B — Generator Correction", badge="AUTO-CORRECT" if args.auto_correct else "PAUSE")
    variant      = state.get("variant", "iter1_weak")
    heatmap_path = ROOT / "charts" / f"{variant[:28]}_auto" / "category_quality_heatmap.png"
    pb_iter      = state.get("phase_b_iter", 1)
    next_variant = f"iter{pb_iter + 1}_corrected"

    if args.auto_correct:
        # ── Auto-correct mode ──────────────────────────────────────────────────
        print(f"\n  [--auto-correct]  LLM will analyse results and suggest a prompt fix.")
        print(f"  Heatmap for reference: {heatmap_path}")
        print(f"  Output prompt: prompts/{next_variant}.txt\n")

        corrected_prompt = _auto_correct_prompt(state, next_variant)

        if corrected_prompt is None:
            # LLM failed or user skipped — fall through to manual instructions
            print("  Falling back to manual Phase B …")
            args.auto_correct = False  # disable for subsequent loops too

    if not args.auto_correct:
        # ── Manual mode ────────────────────────────────────────────────────────
        body = f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  Phase B — Iteration {pb_iter}: Identify and fix the worst segment │
  │                                                                 │
  │  1. OPEN the category × quality heatmap:                       │
  │       {str(heatmap_path):<63}│
  │       Darkest red cell = worst category × dimension to fix.    │
  │                                                                 │
  │  2. CREATE the corrected prompt:                                │
  │       cp prompts/{variant}.txt \\                               │
  │          prompts/{next_variant}.txt                             │
  │       # Edit prompts/{next_variant}.txt                        │
  │       # Add ONE targeted instruction for the failing dimension. │
  │                                                                 │
  │  3. DOCUMENT in iteration_log.md — Iteration {pb_iter + 1}:          │
  │       • Change: what you added to the prompt                   │
  │       • Hypothesis: why this should help                       │
  │                                                                 │
  │  4. Press Enter — pipeline re-generates, re-gates, re-judges.  │
  └─────────────────────────────────────────────────────────────────┘"""
        _pause(f"Phase B iteration {pb_iter} — create prompts/{next_variant}.txt", body)

        corrected_prompt = ROOT / "prompts" / f"{next_variant}.txt"
        while not corrected_prompt.exists():
            print(f"  File not found: {corrected_prompt}")
            p = input("  Enter actual path (or Enter to re-check): ").strip()
            corrected_prompt = ROOT / (p if p else f"prompts/{next_variant}.txt")

    # ── Re-run Steps 1 → 2 → 4 → 5a with the corrected prompt ────────────────
    print(f"\n  Running Steps 1 → 2 → 4 → 5a with: {corrected_prompt.name} …\n")
    state["files"].setdefault("baseline_llm_results", state["files"].get("llm_results"))
    state["variant"] = next_variant

    sub = argparse.Namespace(
        prompt_file=str(corrected_prompt),
        per_category=args.per_category,
        provider=args.provider,
        model=args.model,
        judge_provider=args.judge_provider,
        judge_model=args.judge_model,
        human_count=args.human_count,
        auto_correct=args.auto_correct,
    )
    step1_generate(state, sub)
    step2_gate(state, sub)
    step4_llm_judge(state, sub)
    step5a_charts(state, sub)

    # Before/after comparison chart
    baseline  = state["files"].get("baseline_llm_results")
    corrected = state["files"].get("llm_results")
    if baseline and corrected and baseline != corrected:
        ba_dir = ROOT / "charts" / "before_after"
        ba_dir.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, ROOT / "visualize.py",
              ROOT / baseline, ROOT / corrected,
              "--chart", "before_after", "--output-dir", str(ba_dir)])
        print(f"\n  Before/After : {ba_dir}/before_after.png")
        print(f"  Check the improvement ratio in the chart title (target ≥ 80%).")

    state["phase_b_iter"] = pb_iter + 1
    _save(state)

    again = input("\n  Run another Phase B iteration? [y/N]: ").strip().lower()
    if again == "y":
        step6b_correction(state, args)


def step_final(state: dict) -> None:
    _header("Final — Session Complete", badge="DONE")
    baseline  = state["files"].get("baseline_llm_results")
    corrected = state["files"].get("llm_results")
    if baseline and corrected and baseline != corrected:
        ba_dir = ROOT / "charts" / "before_after"
        ba_dir.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, ROOT / "visualize.py",
              ROOT / baseline, ROOT / corrected,
              "--chart", "before_after", "--output-dir", str(ba_dir)])

    print("""
  ✓ Pipeline complete. Remaining manual steps:

  1. Update the summary table in iteration_log.md
     improvement = (baseline_fail_rate - corrected_fail_rate) / baseline_fail_rate
     Target: ≥ 0.80

  2. Commit results:
       git add iteration_log.md analysis/ prompts/
       git commit -m "Phase B complete: <improvement ratio> failure reduction"

  3. Update README with brief run instructions (required deliverable).
    """)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Guided pipeline orchestrator — Home DIY Repair synthetic data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--prompt-file", default="prompts/iter1_weak.txt",
                   help="Generation prompt template (default: prompts/iter1_weak.txt)")
    p.add_argument("--per-category", type=int, default=12,
                   help="Items per category to generate (default: 12 → 60 total)")
    p.add_argument("--provider", default="groq",
                   choices=list(PROVIDER_DEFAULTS),
                   help="LLM provider for generation (default: groq)")
    p.add_argument("--model", default="",
                   help="Override model name (uses provider default if omitted)")
    p.add_argument("--human-count", type=int, default=20,
                   help="Items to label in human batch (default: 20)")
    p.add_argument("--judge-provider", default="",
                   choices=[""] + list(PROVIDER_DEFAULTS),
                   help=(
                       "LLM provider for the judge (Step 4) and auto-correct synthesis. "
                       "Defaults to --provider (same as generator) if not set. "
                       "Set this to a faster/smarter model (e.g. openai) while keeping "
                       "a weak generator (groq) to preserve baseline failure rates."
                   ))
    p.add_argument("--judge-model", default="",
                   help="Override model for the judge. Uses judge-provider default if omitted.")
    p.add_argument("--auto-correct", action="store_true",
                   help=(
                       "Phase B: use LLM to analyse the worst segment×dimension and suggest "
                       "a targeted prompt addition. You review and approve before re-generation. "
                       "Reduces Phase B time from ~40 min to ~10 min per loop."
                   ))
    p.add_argument("--resume", action="store_true",
                   help="Resume from last saved state")
    p.add_argument("--resume-from", choices=STEP_ORDER, metavar="STEP",
                   help=f"Resume from a specific step: {STEP_ORDER}")
    p.add_argument("--reset", action="store_true",
                   help="Clear saved state and start fresh")
    args = p.parse_args()

    if not args.model:
        args.model = PROVIDER_DEFAULTS.get(args.provider, {}).get("model", "")

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("  State cleared.\n")

    state     = _load_state()
    completed = set(state.get("completed", []))

    if args.resume_from:
        idx = STEP_ORDER.index(args.resume_from)
        for s in STEP_ORDER[:idx]:
            completed.add(s)
        state["completed"] = list(completed)

    # Session header
    _hr()
    print("  Home DIY Repair  —  Pipeline Orchestrator")
    _hr()
    prov_info = f"{args.provider}  ({args.model})" if args.model else args.provider
    judge_info = ""
    if args.judge_provider:
        jm = args.judge_model or PROVIDER_DEFAULTS.get(args.judge_provider, {}).get("model", "default")
        judge_info = f"{args.judge_provider}  ({jm})"
    else:
        judge_info = f"{prov_info}  [same as generator]"
    print(f"  Prompt       : {args.prompt_file}")
    print(f"  Generator    : {prov_info}")
    print(f"  Judge        : {judge_info}")
    print(f"  Items        : {args.per_category * 5} total  ({args.per_category}/category)")
    print(f"  Human labels : {args.human_count} items")
    print(f"  Auto-correct : {'ON  (LLM suggests Phase B prompt fixes)' if args.auto_correct else 'OFF (manual Phase B)'}")
    print(f"  State file   : {STATE_FILE}")
    if completed:
        print(f"  Resuming     : completed → {sorted(completed)}")
    est = "~2–3 hours" if args.auto_correct else "~3–5 hours"
    print(f"\n  Estimated total: {est}")
    _hr()
    print()

    def _do(step_id: str, fn) -> None:
        if step_id in completed:
            print(f"  [SKIP]  Step {step_id} — already completed")
            return
        fn()
        completed.add(step_id)
        state["completed"] = list(completed)
        _save(state)

    _do("1",     lambda: step1_generate(state, args))
    _do("2",     lambda: step2_gate(state, args))
    _do("4",     lambda: step4_llm_judge(state, args))
    _do("5a",    lambda: step5a_charts(state, args))
    _do("3",     lambda: step3_human_label(state, args))
    _do("5b",    lambda: step5b_export(state, args))
    _do("6A",    lambda: step6a_calibration(state, args))
    _do("6B",    lambda: step6b_correction(state, args))
    _do("final", lambda: step_final(state))


if __name__ == "__main__":
    main()
