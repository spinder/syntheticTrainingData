#!/usr/bin/env python3
"""
export_labels.py — Extract structured per-item label records from judge result files.

Reads a human result file (from human_batch.py) and an LLM result file
(from batch_judge.py / promptfoo), matches them by test description, and
produces structured per-item trace records with trace_id and 6-dim verdicts.
Also computes and prints per-dimension human/LLM agreement.

Output files
------------
  <out>_human_labels.json   — list of per-item human label records
  <out>_llm_labels.json     — list of per-item LLM label records
  <out>_agreement.json      — per-dimension agreement rates + summary
  <out>_combined.csv        — all labels in one CSV (labeler column)

Usage
-----
  python3 export_labels.py \\
      --human human/logs/<humanbatch-results>.json \\
      --llm   llm/logs/<batch-results>.json \\
      --out   analysis/iter1_weak_labels
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DIMENSIONS = [
    "answer_completeness",
    "safety_specificity",
    "tool_realism",
    "scope_appropriateness",
    "context_clarity",
    "tip_usefulness",
]

CATEGORY_FULL = {
    "appliance":    "appliance_repair",
    "general_home": "general_home_repair",
    "plumbing":     "plumbing_repair",
    "electrical":   "electrical_repair",
    "hvac":         "hvac_maintenance",
}

# Regex matching "item_0001_appliance | D1 answer_completeness"
_DESC_RE = re.compile(r"item_(\d+)_(\w+)\s*\|\s*D\d+\s+(\w+)")


def _load_results(path: str) -> list[dict]:
    with open(path) as fh:
        data = json.load(fh)
    return data["results"]["results"]


def _extract_verdicts(rows: list[dict]) -> dict[str, bool | None]:
    """Return {description: verdict} from a result list."""
    out = {}
    for row in rows:
        desc = (row.get("testCase") or {}).get("description", "")
        if not desc:
            continue
        output = (row.get("response") or {}).get("output", "")
        if isinstance(output, str):
            normed = output.strip().lower()
            if normed == "pass":
                out[desc] = True
            elif normed == "fail":
                out[desc] = False
    return out


def _build_item_records(verdicts: dict[str, bool | None], labeler: str) -> list[dict]:
    """Group per-description verdicts into per-item records."""
    items: dict[str, dict] = {}
    for desc, verdict in verdicts.items():
        m = _DESC_RE.match(desc)
        if m is None or verdict is None:
            continue
        num, short_cat, dim = m.group(1), m.group(2), m.group(3)
        trace_id = f"qa_{num}"
        category = CATEGORY_FULL.get(short_cat, short_cat)
        if trace_id not in items:
            items[trace_id] = {
                "trace_id": trace_id,
                "category": category,
                "labeler":  labeler,
            }
            for d in DIMENSIONS:
                items[trace_id][d] = None  # will be filled in
        if dim in DIMENSIONS:
            items[trace_id][dim] = 1 if verdict else 0

    # Compute overall_pass (True only when all 6 dims are present and pass)
    for rec in items.values():
        dim_vals = [rec[d] for d in DIMENSIONS]
        if None in dim_vals:
            rec["overall_pass"] = None
        else:
            rec["overall_pass"] = all(v == 1 for v in dim_vals)

    return sorted(items.values(), key=lambda r: r["trace_id"])


def _compute_agreement(human_records: list[dict], llm_records: list[dict]) -> dict:
    """Return per-dim agreement rates on overlapping items."""
    human_map = {r["trace_id"]: r for r in human_records}
    llm_map   = {r["trace_id"]: r for r in llm_records}
    common    = sorted(set(human_map) & set(llm_map))

    if not common:
        return {"n_common_items": 0, "dimensions": {}, "overall_agreement": None}

    dim_agree: dict[str, list[bool]] = defaultdict(list)
    for tid in common:
        h = human_map[tid]
        l = llm_map[tid]
        for dim in DIMENSIONS:
            hv = h.get(dim)
            lv = l.get(dim)
            if hv is not None and lv is not None:
                dim_agree[dim].append(hv == lv)

    dim_rates = {}
    for dim in DIMENSIONS:
        vals = dim_agree[dim]
        dim_rates[dim] = round(sum(vals) / len(vals), 4) if vals else None

    valid_rates = [v for v in dim_rates.values() if v is not None]
    overall     = round(sum(valid_rates) / len(valid_rates), 4) if valid_rates else None

    return {
        "n_common_items":    len(common),
        "dimensions":        dim_rates,
        "overall_agreement": overall,
        "calibrated":        all(v is not None and v >= 0.80 for v in dim_rates.values()),
    }


def _write_csv(human_records: list[dict], llm_records: list[dict], path: Path) -> None:
    fieldnames = ["trace_id", "category", "labeler"] + DIMENSIONS + ["overall_pass"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in human_records + llm_records:
            writer.writerow(rec)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export structured label records from judge result files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--human", required=True,
                        help="Human batch result JSON (from human_batch.py)")
    parser.add_argument("--llm",   required=True,
                        help="LLM batch result JSON (from batch_judge.py / promptfoo)")
    parser.add_argument("--out",   default="analysis/labels",
                        help="Output path stem (default: analysis/labels)")
    args = parser.parse_args()

    human_path = Path(args.human)
    llm_path   = Path(args.llm)

    for p in (human_path, llm_path):
        if not p.exists():
            sys.exit(f"ERROR: {p} not found")

    out_stem = Path(args.out)
    out_stem.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  Loading human: {human_path.name}")
    human_rows = _load_results(str(human_path))
    print(f"  Loading llm  : {llm_path.name}")
    llm_rows   = _load_results(str(llm_path))

    human_verdicts = _extract_verdicts(human_rows)
    llm_verdicts   = _extract_verdicts(llm_rows)

    human_records = _build_item_records(human_verdicts, "human")
    llm_records   = _build_item_records(llm_verdicts,   "llm_judge")

    agreement = _compute_agreement(human_records, llm_records)

    # Write outputs
    human_out = Path(f"{out_stem}_human_labels.json")
    llm_out   = Path(f"{out_stem}_llm_labels.json")
    agree_out = Path(f"{out_stem}_agreement.json")
    csv_out   = Path(f"{out_stem}_combined.csv")

    human_out.write_text(json.dumps(human_records, indent=2))
    llm_out.write_text(json.dumps(llm_records, indent=2))
    agree_out.write_text(json.dumps(agreement, indent=2))
    _write_csv(human_records, llm_records, csv_out)

    print(f"\n  Human labels : {human_out}  ({len(human_records)} items)")
    print(f"  LLM labels   : {llm_out}  ({len(llm_records)} items)")
    print(f"  Agreement    : {agree_out}")
    print(f"  Combined CSV : {csv_out}")

    # Print agreement summary
    n = agreement["n_common_items"]
    print(f"\n  ── Agreement (on {n} common item(s)) ──────────────────────────")
    for dim in DIMENSIONS:
        rate = agreement["dimensions"].get(dim)
        if rate is None:
            print(f"  {dim:<28} : n/a")
        else:
            ok = "✓" if rate >= 0.80 else "✗"
            print(f"  {dim:<28} : {rate:.0%}  {ok}")
    overall = agreement["overall_agreement"]
    if overall is not None:
        calib = "CALIBRATED ✓" if agreement["calibrated"] else "NEEDS CALIBRATION ✗"
        print(f"  {'─'*48}")
        print(f"  {'Overall average':<28} : {overall:.0%}  [{calib}]")
    print()

    if not agreement["calibrated"] and n > 0:
        worst = min(
            ((d, r) for d, r in agreement["dimensions"].items() if r is not None),
            key=lambda x: x[1],
        )
        print(f"  Phase A action: fix judge prompt for '{worst[0]}' (agreement: {worst[1]:.0%})")
        print(f"  Run: ./.projectHistory/promptTools.sh → e (generate rubric draft)\n")


if __name__ == "__main__":
    main()
