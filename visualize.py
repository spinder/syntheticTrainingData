#!/usr/bin/env python3
"""
Generate matplotlib charts from one or more promptfoo result JSON files.

Charts
------
  pass_rate    Per-question pass rate across all supplied runs (bar)
  heatmap      Run × question pass/fail matrix
  agreement    Stacked pass/fail counts per question across runs/judges
  distribution Pass vs fail counts per run (stacked bar)
  all          All of the above (default)

Examples
--------
  python3 visualize.py automated/logs/*.json
  python3 visualize.py automated/logs/*.json --chart heatmap
  python3 visualize.py automated/logs/*.json human/logs/*.json --chart agreement
  python3 visualize.py automated/logs/2026-06-08T10-37-45-automated-results.json --chart pass_rate --output-dir charts/automated
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

PASS_COLOR = "#4CAF50"
FAIL_COLOR = "#F44336"
PARTIAL_COLOR = "#FF9800"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_results(path: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data["results"]["results"]


def run_label(path: str) -> str:
    stem = Path(path).stem
    # "2026-06-08T10-37-45-automated-results" → "10-37-45-automated"
    # keep first 19 chars (date+time) if they look like a timestamp
    if len(stem) >= 19 and stem[4] == "-":
        return stem[:19]
    return stem[:24]


def _verdict(row: dict) -> bool:
    """Return True if the judge said 'pass'. Reads response.output first;
    falls back to gradingResult.pass for assertion-based setups."""
    output = (row.get("response") or {}).get("output", "")
    if isinstance(output, str) and output.strip().lower() in ("pass", "fail"):
        return output.strip().lower() == "pass"
    return bool((row.get("gradingResult") or {}).get("pass", False))


def question_label(row: dict, max_len: int = 26) -> str:
    raw = row["prompt"].get("raw", "")
    label = raw[:max_len] + ("…" if len(raw) > max_len else "")
    return label or f"Q{row['testIdx']}"


def short_q_label(row: dict) -> str:
    return f"Q{row['testIdx']}"


# ---------------------------------------------------------------------------
# Chart: per-dim pass rate
# ---------------------------------------------------------------------------

def chart_pass_rate(runs: list[tuple[str, list]], output_dir: str) -> None:
    """Bar chart: for each question, fraction of runs that passed."""
    idx_passes: dict[int, list[int]] = defaultdict(list)
    idx_label: dict[int, str] = {}

    for _, rows in runs:
        for row in rows:
            idx = row["testIdx"]
            idx_passes[idx].append(1 if _verdict(row) else 0)
            idx_label[idx] = question_label(row)

    indices = sorted(idx_passes)
    labels = [idx_label[i] for i in indices]
    rates = [sum(idx_passes[i]) / len(idx_passes[i]) for i in indices]

    colors = [
        PASS_COLOR if r == 1.0 else FAIL_COLOR if r == 0.0 else PARTIAL_COLOR
        for r in rates
    ]

    fig, ax = plt.subplots(figsize=(max(6, len(indices) * 1.6), 4))
    bars = ax.bar(range(len(indices)), rates, color=colors, edgecolor="white", width=0.6)
    ax.set_xticks(range(len(indices)))
    ax.set_xticklabels(labels, rotation=22, ha="right", fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Pass rate")
    ax.set_title(f"Per-question pass rate  ({len(runs)} run(s))")
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    for bar, rate in zip(bars, rates):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.03,
            f"{rate:.0%}",
            ha="center", va="bottom", fontsize=9, fontweight="bold",
        )
    plt.tight_layout()
    _save(fig, output_dir, "pass_rate.png")


# ---------------------------------------------------------------------------
# Chart: segment heatmap
# ---------------------------------------------------------------------------

def chart_heatmap(runs: list[tuple[str, list]], output_dir: str) -> None:
    """Rows = runs, cols = questions, cells = green(pass) / red(fail)."""
    all_indices = sorted({row["testIdx"] for _, rows in runs for row in rows})
    idx_label: dict[int, str] = {}
    for _, rows in runs:
        for row in rows:
            idx_label[row["testIdx"]] = f"Q{row['testIdx']}: {question_label(row, 18)}"

    col_labels = [idx_label[i] for i in all_indices]
    row_labels = [run_label(p) for p, _ in runs]

    matrix = np.array([
        [1 if {row["testIdx"]: _verdict(row) for row in rows}.get(i, False) else 0
         for i in all_indices]
        for _, rows in runs
    ], dtype=float)

    cmap = mcolors.ListedColormap([FAIL_COLOR, PASS_COLOR])
    fig, ax = plt.subplots(figsize=(max(6, len(all_indices) * 1.6), max(3, len(runs) * 0.65 + 1.8)))
    ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="auto")

    ax.set_xticks(range(len(all_indices)))
    ax.set_xticklabels(col_labels, rotation=22, ha="right", fontsize=8)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=7)
    ax.set_title("Segment heatmap  (green = pass, red = fail)")

    for r in range(matrix.shape[0]):
        for c in range(matrix.shape[1]):
            ax.text(c, r, "✓" if matrix[r, c] else "✗",
                    ha="center", va="center", fontsize=14, color="white", fontweight="bold")

    plt.tight_layout()
    _save(fig, output_dir, "heatmap.png")


# ---------------------------------------------------------------------------
# Chart: agreement
# ---------------------------------------------------------------------------

def chart_agreement(runs: list[tuple[str, list]], output_dir: str) -> None:
    """Stacked bar: for each question, how many runs passed vs failed."""
    idx_pass: dict[int, int] = defaultdict(int)
    idx_fail: dict[int, int] = defaultdict(int)
    idx_label: dict[int, str] = {}

    for _, rows in runs:
        for row in rows:
            idx = row["testIdx"]
            if _verdict(row):
                idx_pass[idx] += 1
            else:
                idx_fail[idx] += 1
            idx_label[idx] = short_q_label(row)

    indices = sorted(idx_pass.keys() | idx_fail.keys())
    labels = [idx_label[i] for i in indices]
    passes = [idx_pass[i] for i in indices]
    fails = [idx_fail[i] for i in indices]
    n = len(runs)

    fig, ax = plt.subplots(figsize=(max(6, len(indices) * 1.4), 4))
    x = range(len(indices))
    ax.bar(x, passes, label="Pass", color=PASS_COLOR)
    ax.bar(x, fails, bottom=passes, label="Fail", color=FAIL_COLOR)
    ax.axhline(n / 2, color="gray", linestyle="--", linewidth=0.8, alpha=0.7, label="50% line")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Count (runs)")
    ax.set_yticks(range(n + 1))
    ax.set_title(f"Agreement chart  ({n} run(s) — full bar = unanimous)")
    ax.legend(fontsize=8)

    for xi, (p, f) in enumerate(zip(passes, fails)):
        if p > 0:
            ax.text(xi, p / 2, str(p), ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        if f > 0:
            ax.text(xi, p + f / 2, str(f), ha="center", va="center", fontsize=9, color="white", fontweight="bold")

    plt.tight_layout()
    _save(fig, output_dir, "agreement.png")


# ---------------------------------------------------------------------------
# Chart: distribution
# ---------------------------------------------------------------------------

def chart_distribution(runs: list[tuple[str, list]], output_dir: str) -> None:
    """Stacked bar per run: pass count vs fail count."""
    labels = [run_label(p) for p, _ in runs]
    passes = [sum(1 for row in rows if _verdict(row)) for _, rows in runs]
    fails = [sum(1 for row in rows if not _verdict(row)) for _, rows in runs]

    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.6), 4))
    ax.bar(x, passes, label="Pass", color=PASS_COLOR)
    ax.bar(x, fails, bottom=passes, label="Fail", color=FAIL_COLOR)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=22, ha="right", fontsize=7)
    ax.set_ylabel("Test count")
    ax.set_title("Score distribution per run")
    ax.legend(fontsize=9)

    total = max((passes[0] + fails[0]) if runs else 1, 1)
    for xi, (p, f) in enumerate(zip(passes, fails)):
        label = f"{p/(p+f):.0%}" if (p + f) > 0 else "n/a"
        ax.text(xi, total + 0.15, label, ha="center", va="bottom", fontsize=8, color="gray")

    plt.tight_layout()
    _save(fig, output_dir, "distribution.png")


# ---------------------------------------------------------------------------
# Shared save helper
# ---------------------------------------------------------------------------

def _save(fig: plt.Figure, output_dir: str, name: str) -> None:
    out = Path(output_dir) / name
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved: {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

CHART_FNS = {
    "pass_rate": chart_pass_rate,
    "heatmap": chart_heatmap,
    "agreement": chart_agreement,
    "distribution": chart_distribution,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate matplotlib charts from promptfoo result JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("results", nargs="+", help="promptfoo JSON result file(s)")
    parser.add_argument(
        "--chart",
        default="all",
        choices=["all"] + list(CHART_FNS),
        help="Chart type (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default="charts",
        help="Output directory for PNG files (default: charts/)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    runs: list[tuple[str, list]] = []
    for path in sorted(args.results):
        try:
            rows = load_results(path)
            runs.append((path, rows))
            print(f"  loaded {path}  ({len(rows)} rows)")
        except Exception as exc:
            print(f"  SKIP {path}: {exc}")

    if not runs:
        print("No valid result files loaded.")
        return

    to_run = list(CHART_FNS.values()) if args.chart == "all" else [CHART_FNS[args.chart]]
    print(f"\nGenerating {len(to_run)} chart(s) → {args.output_dir}/\n")
    for fn in to_run:
        fn(runs, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
