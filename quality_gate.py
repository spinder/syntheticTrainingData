#!/usr/bin/env python3
"""
quality_gate.py — Step 2 data quality gate.

Applies per-item checks (schema validation + lightweight pre-checks per dimension),
deduplication within the batch, and per-category distribution check vs. the
benchmark (20% per category, within 18% tolerance).

Outputs
-------
  <stem>_gated.jsonl       — items that cleared all per-item checks (post-dedup)
  <stem>_gate_report.json  — full per-item and batch-level statistics

Exit codes
----------
  0  — gate passed (distribution OK)
  1  — distribution check failed (regenerate Step 1 before proceeding)

Usage
-----
  python3 quality_gate.py generated_data/iter1_weak_<timestamp>.jsonl
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema.model import HomeDiyRepairQA
from pydantic import ValidationError

# ── Per-dimension pre-check thresholds ────────────────────────────────────────

# D2 Safety Specificity
D2_MIN_SAFETY_LEN = 80
D2_GENERIC_PHRASES = frozenset({
    "be careful", "stay safe", "use caution", "good luck", "be safe",
    "exercise caution", "be cautious", "take care", "work safely",
    "be aware", "proceed carefully",
})

# D3 Tool Realism
D3_TRADE_PHRASES = frozenset({
    "professional-grade", "trade-only", "industrial", "commercial grade",
    "professional equipment", "specialized equipment", "commercial-grade",
})

# D6 Tip Usefulness
D6_MIN_TIP_LEN = 30
D6_GENERIC_PHRASES = frozenset({
    "good luck", "happy fixing", "you can do it", "enjoy", "have fun",
    "be careful", "take your time",
})

CATEGORIES = [
    "appliance_repair",
    "general_home_repair",
    "plumbing_repair",
    "electrical_repair",
    "hvac_maintenance",
]

DISTRIBUTION_MIN_PCT = 0.18  # each category must be ≥ 18% of the batch


# ── Per-item checks ────────────────────────────────────────────────────────────

def _check_item(record: dict) -> list[str]:
    """Return list of failed check identifiers. Empty = all passed."""
    failures = []

    # Schema / structural validation — filter to known model fields only
    core = {k: v for k, v in record.items() if k in HomeDiyRepairQA.model_fields}
    try:
        HomeDiyRepairQA(**core)
    except (ValidationError, Exception) as exc:
        failures.append(f"schema:{exc}")
        return failures  # skip pre-checks if schema is broken

    safety = record.get("safety_info", "")
    tips   = record.get("tips", [])
    tools  = record.get("tools_required", [])

    # D2 — safety_info length
    if len(safety) < D2_MIN_SAFETY_LEN:
        failures.append(f"D2_safety_len:{len(safety)}<{D2_MIN_SAFETY_LEN}")

    # D2 — generic safety phrases
    safety_lower = safety.lower()
    for phrase in D2_GENERIC_PHRASES:
        if phrase in safety_lower:
            failures.append(f"D2_generic:'{phrase}'")
            break

    # D3 — trade-only / professional tools
    tools_str = " ".join(tools).lower()
    for phrase in D3_TRADE_PHRASES:
        if phrase in tools_str:
            failures.append(f"D3_trade:'{phrase}'")
            break

    # D6 — all tips too short
    if tips and all(len(t.strip()) < D6_MIN_TIP_LEN for t in tips):
        failures.append(f"D6_tip_len:all<{D6_MIN_TIP_LEN}")

    # D6 — generic tip phrases
    tips_lower = " ".join(tips).lower()
    for phrase in D6_GENERIC_PHRASES:
        if phrase in tips_lower:
            failures.append(f"D6_generic:'{phrase}'")
            break

    return failures


def _normalize_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.lower().strip().rstrip("?!."))


# ── Main gate logic ────────────────────────────────────────────────────────────

def run_gate(jsonl_path: Path) -> bool:
    """Run the full gate. Returns True if distribution check passes."""
    raw = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    meta_lines = [r for r in raw if not r.get("id", "").startswith("qa_")]
    records    = [r for r in raw if r.get("id", "").startswith("qa_")]

    if not records:
        sys.exit(f"ERROR: no qa_ records found in {jsonl_path}")

    print(f"\n{'═'*60}")
    print(f"  Quality Gate: {jsonl_path.name}")
    print(f"{'═'*60}")
    print(f"  Input    : {len(records)} records\n")

    # ── Per-item checks ────────────────────────────────────────────────────────
    item_results: list[dict] = []
    passed_items: list[dict] = []
    dropped_per_check: Counter = Counter()

    for rec in records:
        failures = _check_item(rec)
        item_results.append({
            "id":       rec["id"],
            "category": rec.get("category", "unknown"),
            "passed":   not failures,
            "failures": failures,
        })
        if failures:
            dropped_per_check.update(failures)
        else:
            passed_items.append(rec)

    n_dropped = len(records) - len(passed_items)
    print(f"  Per-item : {len(passed_items)}/{len(records)} passed  ({n_dropped} dropped)")
    if dropped_per_check:
        for check, count in sorted(dropped_per_check.items(), key=lambda x: -x[1]):
            print(f"             ✗ {check}  ({count} item(s))")

    # ── Deduplication ──────────────────────────────────────────────────────────
    seen: dict[str, str] = {}
    deduped: list[dict]  = []
    dup_ids: list[str]   = []
    item_map = {r["id"]: r for r in item_results}

    for rec in passed_items:
        nq = _normalize_question(rec.get("question", ""))
        if nq in seen:
            dup_ids.append(rec["id"])
            if rec["id"] in item_map:
                item_map[rec["id"]]["failures"].append(f"dup_of:{seen[nq]}")
                item_map[rec["id"]]["passed"] = False
        else:
            seen[nq] = rec["id"]
            deduped.append(rec)

    print(f"  Dedup    : {len(dup_ids)} duplicate(s) removed  →  {len(deduped)} items remain")

    # ── Category distribution check ────────────────────────────────────────────
    total     = len(deduped)
    cat_counts = Counter(r.get("category", "unknown") for r in deduped)
    dist_pass = True

    print(f"\n  Category distribution (benchmark: {DISTRIBUTION_MIN_PCT:.0%} minimum each):")
    for cat in CATEGORIES:
        count = cat_counts.get(cat, 0)
        pct   = count / total if total else 0.0
        ok    = pct >= DISTRIBUTION_MIN_PCT
        if not ok:
            dist_pass = False
        marker = "✓" if ok else "✗"
        print(f"    {marker} {cat:<25}  {count:>3} items  ({pct:.0%})")

    if dist_pass:
        print(f"\n  Distribution : PASS ✓")
    else:
        print(f"\n  Distribution : FAIL ✗  — fix prompt weighting and regenerate Step 1")

    gate_rate = len(deduped) / len(records) * 100 if records else 0.0
    print(f"  Gate pass    : {gate_rate:.1f}%  ({len(deduped)}/{len(records)} items advance)\n")

    # ── Write outputs ──────────────────────────────────────────────────────────
    stem        = jsonl_path.stem
    out_dir     = jsonl_path.parent
    gated_path  = out_dir / f"{stem}_gated.jsonl"
    report_path = out_dir / f"{stem}_gate_report.json"

    with gated_path.open("w") as fh:
        for meta in meta_lines:
            fh.write(json.dumps(meta) + "\n")
        for rec in deduped:
            fh.write(json.dumps(rec) + "\n")

    report = {
        "source":                  str(jsonl_path),
        "total_input":             len(records),
        "passed_per_item_checks":  len(passed_items),
        "duplicates_removed":      len(dup_ids),
        "total_gated":             len(deduped),
        "gate_pass_rate":          round(len(deduped) / len(records), 4) if records else 0.0,
        "distribution_check_pass": dist_pass,
        "distribution_min_pct":    DISTRIBUTION_MIN_PCT,
        "category_counts":         dict(cat_counts),
        "dropped_per_check":       dict(dropped_per_check),
        "items":                   list(item_map.values()),
    }
    with report_path.open("w") as fh:
        json.dump(report, fh, indent=2)

    print(f"  Gated    : {gated_path}")
    print(f"  Report   : {report_path}\n")

    return dist_pass


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 quality_gate.py <path-to.jsonl>")
    ok = run_gate(Path(sys.argv[1]).resolve())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
