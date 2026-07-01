# Architecture

This document describes the pipeline components, data flow, and the reasoning behind each structural decision. For the decision-by-decision rationale, see [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md).

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        GENERATION LAYER                         │
│                                                                 │
│  prompts/iter1_weak.txt                                         │
│         │                                                       │
│         ▼                                                       │
│   generate.py  ──► Instructor ──► LLM Provider ──► Pydantic    │
│         │           (retry on                    validation +   │
│         │           validation                   retry)         │
│         ▼                                                       │
│   generated_data/<variant>_<timestamp>.jsonl                    │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                         QUALITY GATE                            │
│                                                                 │
│   quality_gate.py                                               │
│         │                                                       │
│    Per-item checks:                                             │
│    ├── Schema re-validation (Pydantic)                          │
│    ├── D2: banned generic safety phrases                        │
│    ├── D3: trade-only equipment language                        │
│    ├── D6: generic tip phrases                                  │
│    └── Exact duplicate detection (question text)                │
│         │                                                       │
│    Batch checks:                                                │
│    └── Category distribution (each category 18–22% of batch)   │
│         │                                                       │
│         ├── *_gated.jsonl     ← items that cleared all checks   │
│         └── *_gate_report.json ← full per-item audit trail      │
└─────────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
┌─────────────────────┐       ┌───────────────────────┐
│  LLM JUDGE LAYER    │       │  HUMAN LABEL LAYER    │
│                     │       │                       │
│  batch_judge.py     │       │  human_batch.py       │
│  ── promptfoo eval  │       │  ── interactive TUI   │
│  ── 6 dims × N      │       │  ── [p]ass/[f]ail per │
│     items = N×6     │       │     dimension         │
│     LLM calls       │       │  ── failure reason    │
│  ── auto heatmap    │       │     captured on fail  │
│                     │       │  ── git commit helper │
│  llm/logs/*.json    │       │                       │
└─────────────────────┘       │  human/logs/*.json   │
          │                   └───────────────────────┘
          │                               │
          └───────────────┬───────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AGREEMENT LAYER                           │
│                                                                 │
│   export_labels.py                                              │
│         │                                                       │
│    Cross-references human + LLM verdicts by trace_id           │
│    Outputs per-dimension agreement rates                        │
│         │                                                       │
│         ├── analysis/*_human_labels.json                        │
│         ├── analysis/*_llm_labels.json                          │
│         ├── analysis/*_agreement.json                           │
│         └── analysis/*_combined.csv                             │
└─────────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
   [all dims ≥ 80%]              [any dim < 80%]
          │                               │
          │                      PHASE A: CALIBRATE
          │                      ── revise judge prompt
          │                      ── re-run batch_judge.py
          │                      ── re-check agreement
          │                      ── loop until all ≥ 80%
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE B: CORRECT GENERATOR                   │
│                                                                 │
│   Identify worst category × dimension from LLM judge results   │
│   Read failure notes from git log + session notes              │
│   Call LLM to synthesize targeted prompt addition              │
│   Inject banned phrase list as constraint into synthesis call  │
│   Accept/edit/skip ─► write prompts/iter{N}_corrected.txt      │
│   Re-run Steps 1 → 2 → 4 → 5a automatically                   │
│   Produce before_after.png                                     │
│   Loop until improvement ratio ≥ 80%                           │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VISUALIZATION                              │
│                                                                 │
│   visualize.py                                                  │
│   ── pass_rate.png           per-dimension pass rates           │
│   ── heatmap.png             run × question matrix              │
│   ── category_quality_heatmap.png   category × dim fail rates  │
│   ── category_distribution.png      generated category counts  │
│   ── human_llm_agreement.png        Phase A calibration output │
│   ── before_after.png               Phase B improvement ratio  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Reference

### `generate.py` — Generation

Entry point for Step 1. Uses [Instructor](https://github.com/jxnl/instructor) to wrap LLM API calls and parse responses directly into `HomeDiyRepairQA` Pydantic objects. On Pydantic validation failure, Instructor retries the call automatically (up to `MAX_RETRIES_PER_SLOT=4`). Items that exhaust retries are logged and skipped.

Output JSONL format per line:
```json
{
  "question": "...", "answer": "...", "equipment_problem": "...",
  "tools_required": [...], "steps": [...], "safety_info": "...", "tips": [...],
  "id": "qa_0042", "category": "plumbing_repair",
  "_meta": { "provider": "groq", "model": "llama-3.1-8b-instant",
             "variant": "iter1_weak", "generated_at": "..." }
}
```

The `_meta` block is appended to the raw dict after `model_dump()` — it is not part of the Pydantic schema (which uses `extra="forbid"`).

**Provider support:**

| Provider | Key env var | Notes |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | Default model: `claude-opus-4-7` |
| `openai` | `OPENAI_API_KEY` | Default model: `gpt-4o` |
| `deepseek` | `DEEPSEEK_API_KEY` | OpenAI-compatible API at `api.deepseek.com/v1` |
| `groq` | `GROQ_API_KEY` | Default model: `llama-3.1-8b-instant`; free tier |
| `ollama` | *(none)* | Default model: `llama3.1`; local only |

Override: `--provider <name>`, `--model <name>`, or `LLM_PROVIDER` / `LLM_MODEL` env vars.

---

### `schema/model.py` — Data Contract

Single source of truth for the data schema. All validation, generation prompts, and judge rubrics derive from this model.

```python
class HomeDiyRepairQA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question:          str       = Field(min_length=10,  max_length=500)
    answer:            str       = Field(min_length=20,  max_length=5000)
    equipment_problem: str       = Field(min_length=5,   max_length=300)
    tools_required:    list[str] = Field(min_length=1,   max_length=20)
    steps:             list[str] = Field(min_length=3,   max_length=25)
    safety_info:       str       = Field(min_length=20,  max_length=1000)
    tips:              list[str] = Field(min_length=1,   max_length=10)
    id:                Optional[str]      = Field(default=None, pattern=r"^qa_\d+$")
    category:          Optional[Category] = None
```

JSON Schema is auto-derived from this model via `generate_json_schema.py`. Do not edit `schema/home_diy_repair_qa.schema.json` by hand.

---

### `quality_gate.py` — Pre-filter

Runs after generation, before any LLM judge call. Applies cheap deterministic checks per item, then a batch-level distribution check.

**Per-item checks:**
- Pydantic re-validation (catches items that slipped through Instructor retry)
- D2: `safety_info` must not contain any phrase in `D2_GENERIC_PHRASES` (e.g., `"be careful"`, `"use caution"`, `"be aware"`)
- D2: `safety_info` minimum length of 80 characters
- D3: `tools_required` must not contain trade-only equipment terminology
- D6: tip items must be ≥30 characters; no generic encouragement phrases
- Deduplication: exact question-text match within the batch

**Batch check:**
- Each category must be 18–22% of the gated batch (exit code 1 if any category misses)

The gate produces `*_gate_report.json` with per-item pass/fail/reason for every check.

---

### `batch_judge.py` — LLM Evaluation

Runs the LLM judge against the full gated batch. Renders each item to a temporary text file, generates a transient `promptfoo` config covering all `N items × 6 dimensions`, runs `promptfoo eval`, and produces a category × quality heatmap automatically.

Uses `JUDGE_LLM_PROVIDER` / `JUDGE_LLM_MODEL` env vars. Falls back to `LLM_PROVIDER` / `LLM_MODEL` if no judge override is set.

Output: `llm/logs/<timestamp>-batch-<variant>-results.json`
Auto-chart: `charts/batch_<variant>/category_quality_heatmap.png`

---

### `human_batch.py` — Human Labeling

Interactive terminal tool that presents each item across all 6 dimensions with `[p]ass`, `[f]ail + reason`, or `[s]kip`. Failure reasons are written to `human/logs/.session_notes.txt` in a parseable format:

```
[2026-06-28T18:34:12] [qa_0003_plumbing | D2 safety_specificity] FAIL — says "be careful" with no hazard named
```

After the session, a git commit helper embeds the failure notes into the commit body under a `Failure notes:` header. `generate_rubric.py` reads `git log` to collect all historical failure notes.

---

### `export_labels.py` — Agreement Measurement

Cross-references human and LLM verdict files by `trace_id`. Outputs per-dimension agreement rates and structured label records in four formats (JSON per labeler, combined CSV, agreement summary).

Agreement target: ≥80% per dimension before any Phase B work begins.

---

### `run_pipeline.py` — Orchestrator

Manages the full pipeline with state persistence in `.pipeline_state.json`. Key behaviors:

- **Resumable**: `--resume` continues from the last completed step; `--resume-from <step>` jumps to a specific step
- **Human pause handling**: prints exact, filename-resolved copy-paste commands at each human-action point; waits for Enter
- **Auto-correct**: `--auto-correct` activates Phase B LLM-assisted prompt synthesis with banned-phrase injection
- **Provider forwarding**: accepts `--judge-provider` / `--judge-model` flags; injects them into every subprocess call to `batch_judge.py`

Step order: `1 → 2 → 4 → 5a → [pause: Step 3] → 5b → [Phase A loop] → Phase B loop → final`

Step 3 (human labeling) runs between Steps 4 and 5b by design: the LLM judge runs first so the category × quality heatmap can guide which items are most informative to label.

---

### Judge Pipelines (`automated/`, `human/`, `llm/`)

Three self-contained [promptfoo](https://promptfoo.dev) projects, each with its own `promptfooconfig.yaml`, providers, and question files.

| Pipeline | Trigger | Provider | Question files |
|---|---|---|---|
| `automated/` | Rule-based pre-checks | Python provider (no LLM) | Fixed schema-check questions |
| `human/` | Interactive review | Python provider (TUI) | `q1.txt`–`q6.txt` rubrics |
| `llm/` | LLM evaluation | `llm_judge_provider.py` | Same `q1.txt`–`q6.txt` rubrics |

The human and LLM judges share the same question files so that agreement measurement is comparing answers to identical questions.

---

## Data Flow Summary

Every file produced by the pipeline is timestamped and variant-labeled. The naming convention is:

```
generated_data/
  <variant>_<timestamp>.jsonl            ← raw generation output
  <variant>_<timestamp>_gated.jsonl      ← post-gate
  <variant>_<timestamp>_gate_report.json ← gate audit trail

llm/logs/
  <timestamp>-batch-<variant>-results.json

human/logs/
  <timestamp>-humanbatch-<variant>-results.json

analysis/
  <variant>_<iter>_human_labels.json
  <variant>_<iter>_llm_labels.json
  <variant>_<iter>_agreement.json
  <variant>_<iter>_combined.csv

charts/
  <variant>_auto/
    category_distribution.png
    pass_rate.png
    category_quality_heatmap.png
    human_llm_agreement.png
  before_after/
    before_after.png
```

This makes every run independently reproducible and every artifact traceable to the generation parameters and timestamp that produced it.
