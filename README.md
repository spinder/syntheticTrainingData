# Synthetic Training Data Pipeline

A reproducible pipeline for generating, evaluating, and iteratively improving structured synthetic training data using LLMs — with automated quality gates, multi-provider support, human-in-the-loop calibration, and measurable improvement targets.

This is **Project 1** in a portfolio of AI engineering projects documenting the application of production engineering practices to AI systems development.

---

## What This Demonstrates

- **Pipeline orchestration**: a resumable multi-step pipeline with explicit state management, human-pause points with exact commands, and `--resume-from <step>` recovery
- **Provider abstraction**: five inference backends (Claude, OpenAI, DeepSeek, Groq, Ollama) behind a uniform interface; generator and judge providers independently configured
- **Quality gates**: cheap deterministic pre-filters (schema validation, banned-phrase detection, deduplication, distribution checks) running before expensive LLM judge calls
- **Evaluation calibration**: human/LLM agreement measurement across 6 quality dimensions before any automated metric is trusted
- **Prompt correction feedback loop**: failure-driven, data-traceable prompt iteration with root-cause attribution to specific category × dimension segments
- **Traceability**: failure notes embedded in git history; structured trace records with `trace_id` per item; gate reports per run
- **Reproducibility**: timestamped JSONL outputs, variant labeling, schema pinned to Pydantic model, JSON Schema auto-derived

---

## Background

The dataset domain is Home DIY Repair Q&A. The engineering domain is everything else.

The pipeline generates 60-item batches of structured repair Q&A, gates them through a quality pre-filter, scores them with an LLM judge across 6 dimensions, verifies that judge against human labels, and iterates on the generation prompt until the failure rate drops by ≥80% from baseline.

The baseline run used an intentionally minimal generator configuration (Groq `llama-3.1-8b-instant` with a schema-only prompt) to establish a measurable starting failure rate. The corrected run achieved an **88.3% reduction in failure rate** (9.4% → 1.1%).

See [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) for why the architecture looks the way it does.
See [`docs/blog-synthetic-data-pipeline.md`](docs/blog-synthetic-data-pipeline.md) for the engineering narrative.

---

## Architecture Overview

```
prompts/iter1_weak.txt
        │
        ▼
   generate.py          ← Instructor + Pydantic; 5 providers; 60 items/run
        │
        ▼
  quality_gate.py       ← schema check · banned phrases · dedup · distribution gate
        │
        ├── *_gated.jsonl
        ├── *_gate_report.json
        ▼
  batch_judge.py        ← LLM-as-judge; 6 dims × N items via promptfoo
        │
        ├── human_batch.py    ← human labels on ≥20 items (interactive)
        ▼
 export_labels.py       ← per-dim human/LLM agreement
        │
        ├── Phase A: calibrate judge prompts (if any dim < 80% agreement)
        ▼
Phase B: auto-correct generator prompt → re-run → measure delta
        │
        ▼
  visualize.py → charts/   ← pass_rate · heatmap · distribution · before_after
```

`run_pipeline.py` orchestrates the automated steps. State is persisted to `.pipeline_state.json` after each step. Human steps emit exact, filename-resolved commands.

Full architecture diagram and component rationale: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Repository Layout

```
.
├── generate.py                  # Step 1 — generate JSONL via Instructor + LLM
├── quality_gate.py              # Step 2 — pre-filter before judge
├── batch_judge.py               # Step 4 — LLM batch evaluation
├── human_batch.py               # Step 3 — interactive human labeling
├── export_labels.py             # Step 5b — agreement measurement
├── visualize.py                 # Charts from promptfoo result JSON files
├── run_pipeline.py              # Orchestrator — runs/resumes the full pipeline
├── run.sh                       # Interactive menu (thin wrapper)
│
├── schema/
│   ├── model.py                 # HomeDiyRepairQA — Pydantic model (source of truth)
│   └── home_diy_repair_qa.schema.json  # JSON Schema (auto-derived; do not edit)
│
├── prompts/
│   ├── iter1_weak.txt           # Baseline prompt — intentionally minimal
│   ├── iter2_corrected.txt      # Iter 1 + D3 tool realism fix
│   └── iter3_corrected.txt      # Iter 2 + D2 safety specificity fix
│
├── automated/                   # Rule-based judge pipeline (promptfoo)
├── human/                       # Human judge pipeline (promptfoo)
├── llm/                         # LLM-as-judge pipeline (promptfoo)
│
├── generated_data/              # JSONL outputs: <variant>_<timestamp>[_gated].jsonl
├── analysis/                    # Per-item label records, agreement JSON, combined CSV
├── charts/                      # PNG chart outputs
│
├── validate_record.py           # Validate a single JSONL record against schema
├── validate_schema_self_check.py
│
├── ARCHITECTURE.md
├── DESIGN_DECISIONS.md
├── ENGINEERING_PRINCIPLES.md
│
└── docs/
    ├── blog-synthetic-data-pipeline.md  # Engineering narrative with charts
    └── preview.py                       # Regenerate local HTML preview
```

---

## Quickstart

```bash
# Install dependencies
pip install instructor anthropic openai groq pydantic jsonschema \
            matplotlib numpy pandas pyarrow datasets huggingface_hub
npm install -g promptfoo

# Set providers (split — recommended)
export GROQ_API_KEY="gsk_..."
export LLM_PROVIDER=groq
export LLM_MODEL=llama-3.1-8b-instant

export OPENAI_API_KEY="sk-..."
export JUDGE_LLM_PROVIDER=openai
export JUDGE_LLM_MODEL=gpt-4o-mini

# Run the full pipeline with auto-correct
python3 run_pipeline.py --auto-correct

# Resume after the human labeling pause
python3 run_pipeline.py --resume --auto-correct
```

For the rationale behind the split-provider setup, see [`DESIGN_DECISIONS.md § Generator vs Judge Separation`](DESIGN_DECISIONS.md).

---

## Local Blog Preview

The blog post at `docs/blog-synthetic-data-pipeline.md` references images in `charts/`. To preview it locally with images rendering correctly, serve the repo root as a static site — browsers resolve `../charts/` relative to `/docs/` correctly when served from a common origin.

```bash
# One-time: generate the HTML preview
cd /path/to/syntheticTrainingData
python3 docs/preview.py

# Serve and open
python3 -m http.server 8080
# Open: http://localhost:8080/docs/preview.html
# Stop: Ctrl+C
```

> **Note:** `docs/preview.html` is gitignored — it is a generated artefact. Re-run
> `python3 docs/preview.py` any time you edit the blog markdown. Do not commit it.

---

## Publishing to GitHub Pages

The blog is configured for Jekyll rendering via GitHub Pages. To publish:

**1. Ensure the blog and its images are committed:**
```bash
git add docs/charts/baselineHeatmap.png docs/charts/beforeAfterPassRate.png docs/charts/autoCorrectTerminal.png
git add docs/blog-synthetic-data-pipeline.md docs/preview.py
git commit -m "i)adding blog post, preview helper, and blog chart images."
```

**2. Enable GitHub Pages in the repo settings:**
- Go to **Settings → Pages**
- Source: `Deploy from a branch`
- Branch: `main` / folder: `/docs`
- Save — GitHub will build and publish within ~60 seconds

**3. Your blog will be live at:**
```
https://spinder.github.io/syntheticTrainingData/blog-synthetic-data-pipeline
```

> **Image paths:** The blog images are in `docs/charts/` so they are included in the
> GitHub Pages source root (`/docs`). The blog uses relative paths (`charts/filename.png`)
> which resolve correctly for GitHub.com file preview, GitHub Pages, and local preview.

---

## Key Engineering Concepts

**Generator/judge separation**: The generator and the judge have opposite quality requirements. A weak model as generator produces the failure rate needed to demonstrate improvement. A strong, consistent model as judge produces reliable measurements. They must be independently configured.

**Quality gate ordering**: The gate runs before the LLM judge, not after. Cheap deterministic checks eliminate ≥35% of failures at near-zero cost, improving signal quality and reducing judge API spend.

**Calibration before measurement**: Phase A verifies ≥80% human/LLM agreement per dimension before any judge metric is used to drive prompt changes. An uncalibrated judge that agrees with humans 60% of the time produces measurements that could as easily reflect judge errors as generator errors.

**Failure traceability**: Human labeling failure notes are embedded in git commit messages with a parseable format. The rubric synthesis script reads `git log` directly. Failure history lives in the same store as code history.

**Constraint injection at trust boundaries**: The auto-correct LLM synthesizing prompt additions has no knowledge of what the quality gate bans. The banned phrase list is explicitly injected into every synthesis call. See [`docs/blog-synthetic-data-pipeline.md`](docs/blog-synthetic-data-pipeline.md) — *Phase B: Prompt Injection Whack-a-Mole*.

---

## Further Reading

| Document | Contents |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Pipeline components, data flow, design rationale |
| [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) | Major decisions, alternatives considered, tradeoffs |
| [`ENGINEERING_PRINCIPLES.md`](ENGINEERING_PRINCIPLES.md) | Reusable engineering philosophy for AI systems |
| [`docs/blog-synthetic-data-pipeline.md`](docs/blog-synthetic-data-pipeline.md) | Engineering narrative: the journey, not just the outcome |
