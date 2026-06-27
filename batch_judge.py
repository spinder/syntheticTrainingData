#!/usr/bin/env python3
"""
batch_judge.py — Run the LLM judge against every record in a generated JSONL file.

Each record is rendered as an item text file, a temporary promptfoo config is
generated covering all records × 6 dimensions, promptfoo eval runs, and a
category×quality heatmap is produced automatically.

Usage
-----
  # Basic — uses LLM_PROVIDER / LLM_MODEL env vars (defaults to groq)
  python3 batch_judge.py generated_data/iter1_weak_2026-06-27T16-44-06.jsonl

  # Explicit provider
  LLM_PROVIDER=groq LLM_MODEL=llama-3.1-8b-instant \\
      python3 batch_judge.py generated_data/iter1_weak_*.jsonl

  # Skip chart generation
  python3 batch_judge.py <file> --no-chart

  # Keep the rendered item files after the run (for inspection / human judge)
  python3 batch_judge.py <file> --keep-items

Output
------
  llm/logs/<timestamp>-batch-<variant>-results.json
  charts/batch_<variant>/category_quality_heatmap.png  (unless --no-chart)
"""

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import yaml
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
LLM_DIR      = PROJECT_ROOT / "llm"

DIMENSIONS = [
    "answer_completeness",
    "safety_specificity",
    "tool_realism",
    "scope_appropriateness",
    "context_clarity",
    "tip_usefulness",
]

CATEGORY_SHORT = {
    "appliance_repair":    "appliance",
    "general_home_repair": "general_home",
    "plumbing_repair":     "plumbing",
    "electrical_repair":   "electrical",
    "hvac_maintenance":    "hvac",
}


# ---------------------------------------------------------------------------
# Item file rendering
# ---------------------------------------------------------------------------

def _indent(text: str, prefix: str = "  ") -> str:
    return textwrap.indent(text.strip(), prefix)


def render_item_text(record: dict) -> str:
    """Convert a JSONL record into the item text format used by the evaluation template."""
    lines = [
        "--- Q&A ITEM ---",
        f"question: {record['question']}",
        "",
        f"answer: |\n{_indent(record['answer'])}",
        "",
        f"equipment_problem: {record['equipment_problem']}",
        "",
        "tools_required:",
        *[f"  - {t}" for t in record["tools_required"]],
        "",
        "steps:",
        *[f"  - {s}" for s in record["steps"]],
        "",
        f"safety_info: |\n{_indent(record['safety_info'])}",
        "",
        "tips:",
        *[f"  - {tip}" for tip in record["tips"]],
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Promptfoo config generation
# ---------------------------------------------------------------------------

def build_config(batch_entries: list[dict], variant: str) -> dict:
    """Return a promptfoo config dict for the full batch."""
    tests = []
    for entry in batch_entries:
        short_cat = entry["short_cat"]
        num       = entry["num"]        # zero-padded numeric ID, e.g. "0001"
        filename  = entry["filename"]
        for d_num, d_name in enumerate(DIMENSIONS, 1):
            tests.append({
                "description": f"item_{num}_{short_cat} | D{d_num} {d_name}",
                "vars": {
                    "item":     f"file://questions/items/batch/{filename}",
                    "question": f"file://questions/q{d_num}.txt",
                },
            })
    return {
        "description": f"LLM batch judge — {variant}",
        "prompts":     ["file://prompts/evaluation_template.txt"],
        "providers":   [{"id": "file://providers/llm_judge_provider.py", "label": "llm-judge"}],
        "defaultTest": {
            "assert": [{"type": "javascript",
                        "value": "output.toLowerCase().trim() === 'pass'"}],
        },
        "tests": tests,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the LLM judge against every record in a generated JSONL file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl", help="Path to the generated JSONL file")
    parser.add_argument("--keep-items", action="store_true",
                        help="Keep rendered item files after the run")
    parser.add_argument("--no-chart", action="store_true",
                        help="Skip chart generation")
    parser.add_argument("--chart", default="category_quality",
                        choices=["all", "pass_rate", "heatmap", "agreement",
                                 "distribution", "category_quality"],
                        help="Chart type (default: category_quality)")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl).resolve()
    if not jsonl_path.exists():
        sys.exit(f"ERROR: {jsonl_path} not found")

    variant = jsonl_path.stem  # e.g. "iter1_weak_2026-06-27T16-44-06"

    # Load records (skip any _meta line)
    raw_records = [json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
    records = [r for r in raw_records if r.get("id", "").startswith("qa_")]
    if not records:
        sys.exit("ERROR: no qa_ records found in the JSONL file")

    print(f"\n  Loaded   : {len(records)} record(s) from {jsonl_path.name}")

    # Write item files → llm/questions/items/batch/
    batch_dir = LLM_DIR / "questions" / "items" / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_entries = []
    for record in records:
        item_id   = record.get("id", "qa_0000")          # e.g. "qa_0001"
        num       = item_id.split("_")[-1]               # e.g. "0001"
        category  = record.get("category", "unknown")
        short_cat = CATEGORY_SHORT.get(category, category.split("_")[0])
        filename  = f"{item_id}_{short_cat}.txt"

        (batch_dir / filename).write_text(render_item_text(record))
        batch_entries.append({"num": num, "short_cat": short_cat, "filename": filename})

    n_tests = len(batch_entries) * len(DIMENSIONS)
    print(f"  Items    : {len(batch_entries)} files written to llm/questions/items/batch/")
    print(f"  Tests    : {n_tests} ({len(batch_entries)} items × {len(DIMENSIONS)} dimensions)")

    # Write temporary config
    config      = build_config(batch_entries, variant)
    config_path = LLM_DIR / "promptfooconfig_batch.yaml"
    config_path.write_text(
        "# Auto-generated by batch_judge.py — do not edit; deleted after run\n" +
        yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )

    # Run promptfoo eval (cwd = llm/ so file:// paths resolve correctly)
    timestamp   = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_dir     = LLM_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_file = log_dir / f"{timestamp}-batch-{variant[:28]}-results.json"

    print(f"\n  Running promptfoo eval …\n")
    eval_result = subprocess.run(
        ["promptfoo", "eval",
         "--config", str(config_path),
         "--output", str(output_file)],
        cwd=LLM_DIR,
    )

    # Always clean up the temp config
    config_path.unlink(missing_ok=True)

    if not args.keep_items:
        shutil.rmtree(batch_dir, ignore_errors=True)
    else:
        print(f"\n  Item files kept at: {batch_dir}")

    # promptfoo exits 100 when eval completes but some tests failed — that is
    # expected and not a process error.  Any other non-zero code is a real failure.
    if eval_result.returncode not in (0, 100):
        sys.exit(f"\n  ERROR: promptfoo eval exited with code {eval_result.returncode}")

    print(f"\n  Results  : {output_file}")

    # Auto-generate chart
    if not args.no_chart:
        chart_dir = PROJECT_ROOT / "charts" / f"batch_{variant[:28]}"
        chart_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Charting : {args.chart} → {chart_dir}/\n")
        subprocess.run([
            sys.executable, str(PROJECT_ROOT / "visualize.py"),
            str(output_file),
            "--chart", args.chart,
            "--output-dir", str(chart_dir),
        ], cwd=PROJECT_ROOT)

    print(f"\n  Done.\n")


if __name__ == "__main__":
    main()
