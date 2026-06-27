#!/usr/bin/env python3
"""
human_batch.py — Interactive human judge for a generated JSONL file.

Presents each item from a generated JSONL, prompts the reviewer for a
binary pass/fail verdict on all 6 quality dimensions, and optionally captures
a one-line failure reason per dimension.

Output is saved in a format compatible with visualize.py (mock promptfoo JSON),
so the agreement chart can compare human and LLM verdicts on the same items.
Failure notes are also appended to human/logs/.session_notes.txt.

Usage
-----
  python3 human_batch.py generated_data/iter1_weak_*_gated.jsonl
  python3 human_batch.py generated_data/iter1_weak_*_gated.jsonl --count 20
  python3 human_batch.py generated_data/iter1_weak_*_gated.jsonl --start 10 --count 10
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
NOTES_FILE   = PROJECT_ROOT / "human" / "logs" / ".session_notes.txt"

DIMENSIONS = [
    ("answer_completeness",  "D1 Answer Completeness",
     "Does the answer contain enough detail to complete the repair end-to-end?"),
    ("safety_specificity",   "D2 Safety Specificity",
     "Does safety_info name the SPECIFIC hazard AND the specific precaution (not generic)?"),
    ("tool_realism",         "D3 Tool Realism",
     "Are all tools things a typical homeowner owns or can buy for <$50?"),
    ("scope_appropriateness","D4 Scope Appropriateness",
     "Is the repair within realistic DIY capability, or does it correctly say to call a pro?"),
    ("context_clarity",      "D5 Context Clarity",
     "Does the answer directly address the specific equipment_problem?"),
    ("tip_usefulness",       "D6 Tip Usefulness",
     "Do the tips provide non-obvious, task-specific advice beyond the steps?"),
]

CATEGORY_SHORT = {
    "appliance_repair":    "appliance",
    "general_home_repair": "general_home",
    "plumbing_repair":     "plumbing",
    "electrical_repair":   "electrical",
    "hvac_maintenance":    "hvac",
}


def _fmt(text: str, indent: int = 4, width: int = 76) -> str:
    """Wrap and indent text for display."""
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=" " * indent,
                         subsequent_indent=" " * indent)


def display_item(record: dict, idx: int, total: int) -> None:
    cat = record.get("category", "unknown")
    print(f"\n{'═'*72}")
    print(f"  Item {record.get('id','?')}  [{cat}]  ({idx}/{total})")
    print(f"{'═'*72}")
    print(f"\n  QUESTION:\n{_fmt(record.get('question',''))}")
    print(f"\n  EQUIPMENT PROBLEM:\n{_fmt(record.get('equipment_problem',''))}")
    print(f"\n  ANSWER:\n{_fmt(record.get('answer',''))}")
    tools = record.get("tools_required", [])
    print(f"\n  TOOLS:  {', '.join(tools)}")
    steps = record.get("steps", [])
    print(f"\n  STEPS:")
    for i, s in enumerate(steps, 1):
        print(f"    {i}. {s}")
    print(f"\n  SAFETY INFO:\n{_fmt(record.get('safety_info',''))}")
    tips = record.get("tips", [])
    print(f"\n  TIPS:")
    for tip in tips:
        print(f"    • {tip}")
    print(f"\n{'─'*72}")


def ask_dimension(label: str, description: str) -> tuple[str, str]:
    """Return (verdict, note). verdict = 'pass' | 'fail' | 'skip'."""
    print(f"\n  {label}")
    print(f"  {description}")
    while True:
        raw = input("  [p]ass / [f]ail / [s]kip: ").strip().lower()
        if raw in ("p", "pass"):
            return "pass", ""
        elif raw in ("f", "fail"):
            note = input("  Why? (one line): ").strip()
            return "fail", note
        elif raw in ("s", "skip"):
            return "skip", ""
        print("  Enter p, f, or s.")


def _append_note(label: str, note: str) -> None:
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{label}] FAIL — {note}\n"
    with NOTES_FILE.open("a") as fh:
        fh.write(line)


def _offer_commit(session_notes: list[str]) -> None:
    if not session_notes:
        return
    print(f"\n{'═'*72}")
    print(f"  Session failure notes ({len(session_notes)}):")
    for n in session_notes:
        print(f"    {n.rstrip()}")
    print(f"{'═'*72}")
    ans = input("\n  Generate a git commit command with these notes? [y/N]: ").strip().lower()
    if ans != "y":
        return

    msg_lines = ["Judge run: human batch labeling\n", "Failure notes:"]
    msg_lines += [f"  {n.rstrip()}" for n in session_notes]
    msg_lines.append("\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")
    full_msg = "\n".join(msg_lines)

    print("\n  Run this in your terminal (copy exactly):\n")
    print(f"  git add human/logs/")
    print(f"  git commit -m \"$(cat <<'COMMITMSG'")
    print(full_msg)
    print("COMMITMSG")
    print('  )"')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive human judge for a generated JSONL file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl", help="Path to a generated (or gated) JSONL file")
    parser.add_argument("--count", type=int, default=0,
                        help="Max items to review (0 = all)")
    parser.add_argument("--start", type=int, default=0,
                        help="Zero-based offset into the record list")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl).resolve()
    if not jsonl_path.exists():
        sys.exit(f"ERROR: {jsonl_path} not found")

    variant = jsonl_path.stem

    raw     = [json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
    records = [r for r in raw if r.get("id", "").startswith("qa_")]
    if not records:
        sys.exit("ERROR: no qa_ records found")

    # Slice by start + count
    records = records[args.start:]
    if args.count > 0:
        records = records[:args.count]

    total = len(records)
    print(f"\n  Loaded   : {total} record(s) from {jsonl_path.name}")
    print(f"  Variant  : {variant}")
    print(f"  Reviewing {total} item(s). Enter 'p/f/s' for each dimension.\n")

    # Output goes to human/logs/
    log_dir = PROJECT_ROOT / "human" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_path = log_dir / f"{timestamp}-humanbatch-{variant[:28]}-results.json"

    result_rows  = []
    session_notes: list[str] = []
    test_idx     = 0

    for item_idx, record in enumerate(records, 1):
        display_item(record, item_idx, total)

        item_id   = record.get("id", "qa_0000")
        num       = item_id.split("_")[-1]
        category  = record.get("category", "unknown")
        short_cat = CATEGORY_SHORT.get(category, category.split("_")[0])

        for d_num, (d_key, d_label, d_desc) in enumerate(DIMENSIONS, 1):
            desc    = f"item_{num}_{short_cat} | D{d_num} {d_key}"
            verdict, note = ask_dimension(d_label, d_desc)

            if verdict == "skip":
                test_idx += 1
                continue

            if verdict == "fail" and note:
                _append_note(desc, note)
                ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                session_notes.append(f"[{ts}] [{desc}] FAIL — {note}")

            result_rows.append({
                "testIdx":  test_idx,
                "testCase": {"description": desc, "vars": {}},
                "prompt":   {"raw": ""},
                "response": {"output": verdict},
                "gradingResult": {"pass": verdict == "pass"},
            })
            test_idx += 1

        # Ask whether to continue after each item (except last)
        if item_idx < total:
            cont = input("\n  [Enter] next item  |  [q] quit and save: ").strip().lower()
            if cont == "q":
                print("  Stopping early — saving results so far.")
                break

    # Save results in mock-promptfoo format (compatible with load_results() in visualize.py)
    output = {
        "version": "humanbatch-1.0",
        "results": {
            "results": result_rows,
        },
    }
    output_path.write_text(json.dumps(output, indent=2))
    n_labeled = len({r["testCase"]["description"].split("|")[0].strip() for r in result_rows})
    n_fail    = sum(1 for r in result_rows if r["response"]["output"] == "fail")
    print(f"\n  Saved    : {output_path}")
    print(f"  Items    : {n_labeled}  |  Rows: {len(result_rows)}  |  Fails: {n_fail}")

    _offer_commit(session_notes)
    print("\n  Done.\n")


if __name__ == "__main__":
    main()
