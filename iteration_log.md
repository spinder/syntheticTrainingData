# Iteration Log — Home DIY Repair Synthetic Data Pipeline

Tracks every prompt correction cycle (generator or judge) with hypothesis,
quantitative result, and decision. Required deliverable for the mini-project.

---

## Summary Table

| # | Date | Phase | Change | Min Human/LLM Agr. | Overall Fail Rate | Decision |
|---|------|-------|--------|---------------------|-------------------|---------|
| 1 | — | Baseline | Initial weak prompt + default judge | — | — | Establish baseline |

---

## Iteration 1 — Baseline

- **Date**: (fill in after generating 60-item baseline)
- **Phase**: Baseline
- **Change**: `prompts/iter1_weak.txt` — minimal prompt (field names + schema only, no quality coaching)
- **Hypothesis**: Thin prompt with weak model (Groq llama-3.1-8b-instant) will produce a measurable failure rate ≥ 15% across quality dimensions, establishing a baseline to improve against
- **Result**: (fill in after running batch_judge + human_batch)
  - Items generated: —
  - Items gated (Step 2 pass rate): —
  - LLM judge overall pass rate: —
  - Human labels collected: —
  - Human/LLM agreement per dim:
    - D1 Answer Completeness: —
    - D2 Safety Specificity: —
    - D3 Tool Realism: —
    - D4 Scope Appropriateness: —
    - D5 Context Clarity: —
    - D6 Tip Usefulness: —
- **Decision**: Baseline established. Move to Phase A (judge calibration) if any dim < 80% agreement; else go direct to Phase B.
- **Next step**: Review `charts/iter1_weak/human_llm_agreement.png`. Fix worst-agreement dimension in judge prompt.

---

## Iteration 2 — (Phase A or B)

- **Date**:
- **Phase**: A (judge calibration) | B (generator correction)
- **Change**: (what prompt file was changed and what specifically was added/removed)
- **Hypothesis**: (why this change should improve the failing dimension)
- **Result**:
  - Items generated: —
  - LLM judge overall pass rate: —
  - Human/LLM agreement per dim: (copy from export_labels.py output)
  - Worst dimension before: — @ —%  |  after: — @ —%
- **Decision**: Keep / Revert / Modify further
- **Next step**:

---

## Iteration 3 — (Phase A or B continued)

- **Date**:
- **Phase**:
- **Change**:
- **Hypothesis**:
- **Result**:
- **Decision**:
- **Next step**:

---

## Iteration 4 — (Phase B — generator correction)

- **Date**:
- **Phase**: B
- **Change**:
- **Hypothesis**:
- **Result**:
  - Baseline overall fail rate: —%
  - Post-correction overall fail rate: —%
  - Improvement ratio: (baseline_fail - corrected_fail) / baseline_fail = —%
  - Target: ≥ 80% improvement
- **Decision**:
- **Next step**:

---

## Before / After Summary (fill in at end of Phase B)

| Dimension | Baseline Pass Rate | Corrected Pass Rate | Delta |
|---|---|---|---|
| D1 Answer Completeness | — | — | — |
| D2 Safety Specificity | — | — | — |
| D3 Tool Realism | — | — | — |
| D4 Scope Appropriateness | — | — | — |
| D5 Context Clarity | — | — | — |
| D6 Tip Usefulness | — | — | — |
| **Overall** | — | — | — |

**Improvement ratio**: `(baseline_fail - corrected_fail) / baseline_fail`  
**Target**: ≥ 0.80 (> 80% reduction in failure rate)

---

## Phase A Completion Criteria

- [ ] All 6 dimensions reach ≥ 80% human/LLM agreement
- [ ] Agreement verified by re-running `export_labels.py` after judge prompt revision
- [ ] Chart saved: `charts/<iter>/human_llm_agreement.png`

## Phase B Completion Criteria

- [ ] Baseline overall failure rate ≥ 15% (pipeline detects real problems)
- [ ] Post-correction overall failure rate ≤ 20% of baseline (> 80% reduction)
- [ ] Post-correction dataset meets ≥ 80% overall pass rate across all 6 dimensions
- [ ] Before/after chart saved: `charts/before_after/before_after.png`
- [ ] All prompt changes are data-driven (traceable to specific segment + dimension)
