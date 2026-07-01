# Design Decisions

This document records the major architectural and engineering decisions made during the development of this pipeline, including alternatives considered, the reasoning that drove each choice, and the tradeoffs accepted.

---

## 1. Generator vs Judge Separation

**Decision**: Use independent environment variables (`JUDGE_LLM_PROVIDER` / `JUDGE_LLM_MODEL`) for the evaluation judge, separate from the generator (`LLM_PROVIDER` / `LLM_MODEL`).

**Why it matters**: The generator and judge have opposite quality requirements:
- The generator needs a deliberately constrained model configuration. The project measures improvement from a baseline failure rate. A capable model following a minimal prompt may produce near-perfect output, collapsing the baseline failure rate and making the ≥80% improvement target unreachable. The constrained configuration isn't a limitation — it's a controlled variable.
- The judge needs a *consistent, accurate* model. Measurement reliability depends on the judge making the same call the same way on equivalent items. A stronger model produces more consistent verdicts.

**How it surfaced**: The original implementation used a single `LLM_PROVIDER` for both. When rate-limiting on Groq's free tier (6K TPM) created pressure to switch to a paid OpenAI model, the effect on the baseline measurement became clear: switching `LLM_PROVIDER` to `gpt-4o-mini` would make the judge more accurate *and* the generator produce higher-quality output. The improvement measurement would be confounded.

**Implementation**: `llm_judge_provider.py` reads `JUDGE_LLM_PROVIDER` first, falling back to `LLM_PROVIDER`. `run_pipeline.py` accepts `--judge-provider` / `--judge-model` flags and propagates them to every subprocess call that invokes the judge. Neither file has a hardcoded provider choice.

**Tradeoff accepted**: Two env var pairs instead of one adds setup friction. The `AreAllSettingsDependenciesInPlace.sh` validation script mitigates this by checking that all required vars are set before the pipeline runs. A unified config file would be cleaner for production; env vars were chosen to avoid adding a config parsing dependency.

---

## 2. Quality Gate Ordering

**Decision**: Run the quality gate (`quality_gate.py`) before the LLM judge, not after or in parallel.

**Why**: The gate uses cheap deterministic checks — keyword matching, length thresholds, duplicate detection, Pydantic re-validation. These catch a predictable class of clearly wrong items at essentially zero cost (< 1 second for 60 items). The LLM judge calls cost API spend and time (360 calls for a 60-item batch × 6 dimensions). Running the gate first eliminates items that would fail the judge for trivial reasons, improving signal quality and reducing cost.

**Observed result**: The gate rejected ~35% of items in the iter1 baseline run before any LLM judge calls were made. That 35% was "definitely wrong" by cheap criteria — generic safety phrases, schema violations, duplicates. The LLM judge then operated on the remaining 65% where the quality determination was genuinely ambiguous.

**Alternative considered**: Running the LLM judge first and using its verdicts to filter. This is strictly more expensive and provides no information the gate doesn't already cover for the categories the gate checks. The gate handles the clear cases; the judge handles the uncertain ones.

**Tradeoff accepted**: The gate's keyword-based checks are brittle — they catch known bad patterns, not unknown ones. Items with novel forms of bad safety language that don't match the banned phrase list pass the gate and appear in judge results. The gate is not a replacement for the judge; it's a pre-filter.

---

## 3. Resumable Execution

**Decision**: Persist pipeline state to `.pipeline_state.json` after every completed step, with `--resume`, `--resume-from <step>`, and `--reset` flags.

**Why**: The pipeline has a mandatory human-in-the-loop pause at Step 3 (human labeling, ~40 minutes). Without state persistence, a crash or a session restart before that step completes would require re-running generation (8+ minutes on Groq) and the LLM judge (8+ minutes, 360 API calls). For a 2–3 hour pipeline, non-resumability makes any interruption expensive.

**Implementation**: `.pipeline_state.json` stores the step number, all generated filenames, the variant label, provider config, and item counts after each step. `--resume` reads this file and continues from the last persisted step. `--resume-from 6B` skips all steps before 6B using the filenames already recorded in state.

**Design choice**: State is a flat JSON file, not a database. The pipeline runs once at a time; concurrent state modification is not a concern. JSON is directly inspectable for debugging.

**Tradeoff**: `.pipeline_state.json` is gitignored. If the state file is lost, the pipeline restarts. Filenames embed timestamps so previously-generated JSONL files are still present in `generated_data/`; they just need to be referenced manually if state is lost.

---

## 4. Evaluation Calibration (Phase A)

**Decision**: Require ≥80% human/LLM agreement per quality dimension before using LLM judge verdicts to drive prompt corrections.

**Why**: An LLM judge that agrees with humans 60% of the time is effectively random on close calls. If Phase B prompt corrections are driven by that judge's measurements, the "improvements" being made are in response to noise rather than signal. The calibration gate enforces that the measuring instrument is reliable before it drives decisions.

**How calibration works**: After the first LLM judge run and human labeling pass on the same items, `export_labels.py` computes per-dimension agreement. Dimensions below 80% get their judge prompts revised — typically by adding concrete pass/fail examples that eliminate ambiguity. The LLM judge re-runs against the same gated batch. This loops until all 6 dimensions reach ≥80%.

**Failure note traceability**: Human labeling failure reasons are captured in `human/logs/.session_notes.txt` and embedded in git commit messages under a `Failure notes:` header by `human_batch.py`'s commit helper. `generate_rubric.py` reads `git log` to collect all historical failure notes and synthesizes improved rubric criteria. The failure history lives in the commit store rather than a separate artifact.

**Tradeoff**: Phase A can require multiple judge re-runs, each costing time and API spend. In practice, one or two rubric revisions were sufficient to reach calibration. The cost is justified: operating Phase B against an uncalibrated judge invalidates the improvement measurement.

---

## 5. Prompt Correction Workflow

**Decision**: Use an LLM call to synthesize prompt additions (Phase B `--auto-correct`), with the complete banned phrase list explicitly injected as a constraint into every synthesis call.

**Why it works this way**: The auto-correct mechanism identifies the worst-performing category × dimension segment (e.g., `plumbing × safety_specificity`), reads failure notes from git history, and generates a targeted 2–5 sentence addition to the generation prompt. The intent is that each correction addresses a specific, evidence-based failure pattern rather than adding generic guidance.

**Why the constraint injection matters**: The auto-correct LLM has no knowledge of what `quality_gate.py` bans. In early testing, it generated a prompt addition for D2 (Safety Specificity) containing the phrase `"be aware"` in a positive example sentence. `"be aware"` is in `D2_GENERIC_PHRASES`. The generator learned the phrase from the positive example and started producing it at scale; the next run had 37 of 60 items rejected by the gate for exactly that phrase.

After this incident, the `_auto_correct_prompt()` function in `run_pipeline.py` injects the full banned phrase list before every LLM synthesis call:

```python
forbidden_block = (
    "\n## CRITICAL — Forbidden phrases (quality gate hard-rejects these)\n"
    "NEVER use any of these phrases in your suggested addition — not even inside\n"
    "a positive 'for example' sentence...\n"
    f"  {banned_phrases}\n"
)
```

**Principle generalized**: Any LLM whose output feeds back into the pipeline is producing input to a downstream system that has its own constraints. Those constraints must be explicitly communicated to the LLM — they cannot be assumed. The same applies to any trust boundary in a production system.

**Tradeoff**: The auto-correct LLM's suggestions must be reviewed before acceptance (`[a]ccept / [e]dit / [s]kip`). Fully automatic application without human review creates a feedback loop with no circuit breaker. The human review step also makes prompt changes attributable — the accepted suggestion is written to a versioned file (`prompts/iter{N}_corrected.txt`) and committed.

---

## 6. Provider Abstraction

**Decision**: Abstract all LLM providers behind a uniform interface: set provider name and model via env var or CLI flag; the rest of the code doesn't branch on provider identity.

**Implementation**: `generate.py` resolves the provider at startup and returns an `instructor`-wrapped client. All downstream code calls the client uniformly. `llm_judge_provider.py` checks provider identity only once at initialization to select the right base URL and key. No other file has provider-specific logic.

**Why**: Provider lock-in in AI systems is a real operational risk. Rate limits, pricing changes, model deprecations, and availability issues all create pressure to switch providers mid-project. A system where provider identity is checked in ten places requires ten changes to switch. A system where it's checked in one place requires one.

**What "provider abstraction" doesn't solve**: Model behavior differences across providers are real and affect quality. When the generator switched from Groq `llama-3.1-8b-instant` to OpenAI `gpt-4o-mini` between iter2 and iter3, the failure rate dropped partly because `gpt-4o-mini` is a better instruction-follower, not solely because the prompt improved. Abstraction at the API layer doesn't abstract away model capability differences. Those require controlled experiments to isolate.

---

## 7. Human-in-the-Loop Design

**Decision**: Make human labeling a first-class step in the pipeline orchestration with a formal pause, exact copy-paste commands, and structured failure note capture.

**Why formal**: Informal human review (spot-checking, subjective impressions) doesn't produce data. Formal human labeling with per-dimension binary verdicts and structured failure reasons produces data that can drive rubric calibration and failure note synthesis. The difference between "this doesn't feel right" and `[2026-06-28T18:34:12] [qa_0003_plumbing | D2 safety_specificity] FAIL — says "be careful" with no hazard named` is the difference between intuition and a training signal.

**Why the orchestrator pauses at Step 3 after Step 4**: The LLM judge runs before human labeling so that the category × quality heatmap is available as a guide. Human labelers can focus on items from the highest-failure segments, making the 20-item human review more informative than a random sample.

**Bottleneck acknowledgment**: Human labeling 20 items across 6 dimensions takes 40–60 minutes of focused attention. It is the only step in the pipeline that doesn't scale with compute. Pipeline design should minimize how many times it needs to happen.

---

## 8. Schema as Source of Truth

**Decision**: Define the data model once in `schema/model.py` (Pydantic) and derive all other representations from it.

**Chain**: `schema/model.py` → `generate_json_schema.py` → `schema/home_diy_repair_qa.schema.json` → `validate_schema_self_check.py` / `validate_record.py` / `validate_hf_dataset.py`.

**Why**: If the Pydantic model and the JSON Schema diverge, validation silently fails in some paths and not others. Deriving the JSON Schema from the Pydantic model guarantees consistency. The generation prompt's field descriptions are kept aligned with model constraints manually — a known gap that a future schema annotation approach (e.g., `Field(description=...)`) could close.

**`extra="forbid"` rationale**: Prevents the LLM from inventing fields. Instructor retries on validation failure, so extra fields trigger a retry rather than silently appearing in output. This is strict by design — it's better to retry than to corrupt the dataset with unspecified fields.

---

## Known Gaps and Future Work

| Gap | Impact | Mitigation |
|---|---|---|
| Model switch between iter2 and iter3 confounds improvement measurement | Improvement ratio includes model capability delta | Documented explicitly; controlled comparison not run due to time |
| Gate's banned phrase list is manually maintained | Novel generic phrases not in the list pass the gate | LLM judge catches them; gate catches the most common patterns |
| Auto-correct synthesizes one correction per loop | Multiple failing dimensions per run → multiple loops needed | Acceptable for current iteration count |
| `iteration_log.md` requires manual updates | Entries can fall out of sync with actual runs | Future: auto-generate from `.pipeline_state.json` entries |
| Duplicate rate (~15% in iter3) signals over-constraint | Prompt constraints narrowing scenario space | Monitor dedup rate as a leading indicator; widen if >10% |

---

*← [README](README.md) · [Architecture](ARCHITECTURE.md) · [Engineering Principles](ENGINEERING_PRINCIPLES.md)*
