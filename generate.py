#!/usr/bin/env python3
"""
Step 1 — Synthetic Data Generator

Generates Home DIY Repair Q&A items using Instructor + your choice of LLM provider.
All three providers emit the same 7-field schema; output JSONL is identical.

Providers
---------
  claude    (default)  Anthropic Claude — set ANTHROPIC_API_KEY
  openai               OpenAI GPT       — set OPENAI_API_KEY
  deepseek             DeepSeek         — set DEEPSEEK_API_KEY

Usage
-----
  # Full baseline — 60 items across 5 categories (default)
  export ANTHROPIC_API_KEY="sk-ant-..."
  python3 generate.py

  # Switch provider / model
  python3 generate.py --provider openai   --model gpt-4o
  python3 generate.py --provider openai   --model gpt-4o-mini
  python3 generate.py --provider deepseek --model deepseek-chat

  # Smaller smoke test
  python3 generate.py --per-category 3

  # Label a corrected-prompt run
  python3 generate.py --variant corrected_v2

Output
------
  generated_data/<variant>_<timestamp>.jsonl
  Each line: all 7 schema fields + pipeline metadata (_meta block).
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import instructor
import openai
from pydantic import ValidationError

from schema.model import HomeDiyRepairQA

# ---------------------------------------------------------------------------
# Provider defaults
# ---------------------------------------------------------------------------

PROVIDER_DEFAULTS: dict[str, str] = {
    "claude":   "claude-opus-4-7",
    "openai":   "gpt-4o",
    "deepseek": "deepseek-chat",   # maps to their current best chat model
}

DEFAULT_PROVIDER         = "claude"
DEFAULT_ITEMS_PER_CATEGORY = 12      # 60 total; above the ≥50 target
MAX_RETRIES_PER_SLOT     = 4
INTER_REQUEST_DELAY      = 0.5       # seconds between API calls

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES = [
    "appliance_repair",
    "general_home_repair",
    "plumbing_repair",
    "electrical_repair",
    "hvac_maintenance",
]

CATEGORY_LABELS = {
    "appliance_repair":    "Appliance Repair — refrigerators, washing machines, dryers, dishwashers, ovens",
    "general_home_repair": "General Home Repair — drywall, doors/windows, flooring, basic carpentry",
    "plumbing_repair":     "Plumbing Repair — leaks, clogs, fixture repairs, pipe problems",
    "electrical_repair":   "Electrical Repair — outlet replacement, switch repair, light fixture installation (safe homeowner-level work only; no main panel or gas)",
    "hvac_maintenance":    "HVAC Maintenance — filter changes, thermostat issues, vent cleaning, basic troubleshooting",
}

# ---------------------------------------------------------------------------
# Generation prompt  (baseline_v1 — keep variant label in sync when editing)
# ---------------------------------------------------------------------------

DEFAULT_VARIANT = "baseline_v1"

GENERATION_PROMPT = """\
You are generating a training data item for a Home DIY Repair assistant dataset.
Category: {category_label}

Generate ONE realistic repair scenario that a typical homeowner might face in this category.
Each call should produce a DIFFERENT specific problem — vary the appliance, fixture, or component.

Strict requirements for each field:

question
  Write it as a homeowner would ask: describe the symptom clearly.
  Example: "My washing machine fills with water but the drum never spins — what do I do?"

answer
  Write a coherent narrative (700–1300 characters) that weaves together the tools,
  steps, safety, and tips. Do NOT just list fields — explain the repair as you would
  to a first-time DIYer reading over their shoulder.

equipment_problem
  The specific component and symptom in plain language, e.g. "washing machine drum not spinning".

tools_required
  ONLY tools a typical homeowner already owns or can buy at a hardware store for under $50.
  No professional, trade-only, or specialty equipment.

steps
  At least 3 concrete, numbered steps. Each step must be specific enough to follow without
  guessing — include quantities, measurements, or observable indicators where relevant.

safety_info
  MUST name the SPECIFIC hazard of this repair AND the SPECIFIC precaution that prevents it.
  FAIL examples (too generic): "be careful", "stay safe", "exercise caution".
  PASS example: "A dryer runs on 240V — unplug it from the wall outlet and confirm no
  current with a non-contact tester before removing the back panel."

tips
  At least 1 non-obvious, task-specific tip that adds value a beginner would not know
  from the steps alone. Do NOT restate a step or give generic encouragement.
  FAIL: "Take your time and double-check your work."
  PASS: "If the new thermal fuse blows again within a few weeks, the exhaust duct is
  still clogged — clean it from dryer to wall exit before replacing the fuse a third time."
"""

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def build_client(provider: str) -> tuple[instructor.Instructor, str]:
    """Return (instructor_client, api_type) where api_type is 'anthropic' or 'openai'."""
    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY is not set — see SETUP.txt for instructions.")
        return instructor.from_anthropic(anthropic.Anthropic(api_key=key)), "anthropic"

    elif provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("OPENAI_API_KEY is not set — see SETUP.txt for instructions.")
        return instructor.from_openai(openai.OpenAI(api_key=key)), "openai"

    elif provider == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("DEEPSEEK_API_KEY is not set — see SETUP.txt for instructions.")
        # DeepSeek exposes an OpenAI-compatible endpoint
        return instructor.from_openai(
            openai.OpenAI(api_key=key, base_url="https://api.deepseek.com/v1")
        ), "openai"

    else:
        raise SystemExit(f"Unknown provider '{provider}'. Choose: claude, openai, deepseek")


# ---------------------------------------------------------------------------
# Single-item generation
# ---------------------------------------------------------------------------

def generate_one(
    client: instructor.Instructor,
    api_type: str,
    model: str,
    category: str,
    generation_prompt: str = GENERATION_PROMPT,
) -> HomeDiyRepairQA | None:
    prompt = generation_prompt.format(category_label=CATEGORY_LABELS[category])
    kwargs = dict(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        response_model=HomeDiyRepairQA,
    )
    try:
        if api_type == "anthropic":
            return client.messages.create(**kwargs)
        else:  # openai-compatible (openai, deepseek)
            return client.chat.completions.create(**kwargs)
    except ValidationError as exc:
        print(f"      [validation error] {exc.error_count()} field(s) failed schema — skipping")
        return None
    except Exception as exc:
        print(f"      [error] {type(exc).__name__}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic DIY repair Q&A items",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--provider", default=DEFAULT_PROVIDER,
        choices=["claude", "openai", "deepseek"],
        help=f"LLM provider (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model name override (defaults: claude→claude-opus-4-7, openai→gpt-4o, deepseek→deepseek-chat)",
    )
    parser.add_argument(
        "--per-category", type=int, default=DEFAULT_ITEMS_PER_CATEGORY,
        help=f"Items to generate per category (default: {DEFAULT_ITEMS_PER_CATEGORY})",
    )
    parser.add_argument(
        "--variant", default=DEFAULT_VARIANT,
        help=f"Prompt variant label written to _meta (default: {DEFAULT_VARIANT})",
    )
    parser.add_argument(
        "--output-dir", default="generated_data",
        help="Directory for output JSONL files (default: generated_data/)",
    )
    parser.add_argument(
        "--prompt-file", default=None,
        help="Path to a .txt prompt template containing {category_label}. "
             "Overrides the built-in GENERATION_PROMPT. "
             "Auto-sets --variant to the file stem when --variant is not specified.",
    )
    args = parser.parse_args()

    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            raise SystemExit(f"--prompt-file not found: {args.prompt_file}")
        generation_prompt = prompt_path.read_text()
        if "{category_label}" not in generation_prompt:
            raise SystemExit(
                f"--prompt-file '{args.prompt_file}' must contain the placeholder {{category_label}}"
            )
        if args.variant == DEFAULT_VARIANT:
            args.variant = prompt_path.stem
    else:
        generation_prompt = GENERATION_PROMPT

    model = args.model or PROVIDER_DEFAULTS[args.provider]
    client, api_type = build_client(args.provider)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(exist_ok=True)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_path = out_dir / f"{args.variant}_{run_ts}.jsonl"

    target = args.per_category * len(CATEGORIES)
    print(f"Provider : {args.provider}  ({model})")
    print(f"Target   : {args.per_category} × {len(CATEGORIES)} categories = {target} items")
    print(f"Output   : {out_path}\n")

    item_counter = 1
    total_written = 0
    total_errors = 0

    with open(out_path, "w") as f:
        for category in CATEGORIES:
            print(f"  [{category}]")
            written_this_cat = 0
            attempts = 0

            while written_this_cat < args.per_category:
                attempts += 1
                if attempts > args.per_category * MAX_RETRIES_PER_SLOT:
                    print(f"    !! gave up on {category} after {attempts} attempts")
                    break

                item = generate_one(client, api_type, model, category, generation_prompt)
                if item is None:
                    total_errors += 1
                    time.sleep(1)
                    continue

                item.id = f"qa_{item_counter:04d}"
                item.category = category

                record = {
                    **item.model_dump(exclude_none=False),
                    "_meta": {
                        "trace_id":       item.id,
                        "prompt_variant": args.variant,
                        "category":       category,
                        "provider":       args.provider,
                        "model":          model,
                        "timestamp":      datetime.now(timezone.utc).isoformat(),
                    },
                }

                f.write(json.dumps(record) + "\n")
                f.flush()

                written_this_cat += 1
                total_written += 1
                item_counter += 1
                print(f"    {item.id}  {item.equipment_problem[:65]}")
                time.sleep(INTER_REQUEST_DELAY)

    print(f"\n{'─' * 52}")
    print(f"Written  : {total_written} items")
    print(f"Errors   : {total_errors}")
    print(f"File     : {out_path}")
    if total_written < 50:
        print(f"WARNING  : {total_written} < 50 minimum — re-run or increase --per-category")


if __name__ == "__main__":
    main()
