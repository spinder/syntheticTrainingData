# Engineering Principles for AI Systems

This document describes engineering principles developed through building production-grade AI data pipelines. These principles are intended to be shared across a portfolio of AI engineering projects; each project applies and refines them.

They are not rules for a specific domain. They are engineering habits that transfer from traditional software and operational systems into AI systems — with appropriate adjustments for the non-determinism that AI introduces.

---

## 1. Define Quality Before You Measure It

A quality metric is only meaningful if its definition is fixed before the measurement runs. Defining quality as "whatever the LLM produces" makes improvement unmeasurable. Defining quality as "safety_info must name a specific hazard AND a specific precaution" gives you a criterion that can be checked consistently across runs, models, and time.

**In practice:**
- Define your evaluation dimensions before your first generation run
- Write the evaluation criteria as a rubric that a judge — human or LLM — can apply consistently
- The rubric is a contract; changes to it break comparability between runs

**What fails without this:**
When quality criteria are defined after the fact to match output that already exists, you've built a measurement system that proves the baseline was fine. That's not evaluation; it's rationalization.

---

## 2. Calibrate Instruments Before Trusting Measurements

A measurement system that isn't calibrated produces numbers that cannot be trusted to drive decisions. This applies to automated test suites, monitoring dashboards, static analysis rules, and LLM judges equally.

**In practice:**
- Run a human labeling pass on the same items the automated judge scores
- Compute agreement per evaluation dimension
- Do not use automated judge verdicts to drive iteration until agreement exceeds a defined threshold (≥80% per dimension is a reasonable starting point)
- When agreement is low, fix the judge first; the generator problem may be obscured by judge noise

**The asymmetry to remember:**
A judge that's too strict produces false failures that make the generator look worse than it is. A judge that's too permissive produces false passes that make the generator look better. Both are wrong, but in different directions. Calibration identifies which direction the bias runs.

---

## 3. Cheap Gates Before Expensive Gates

Filters should be ordered from cheapest to most expensive, applied strictly in that order.

**In practice:**
- Run rule-based, keyword-based, and schema-based checks before any LLM call
- The rule-based gate catches "definitely wrong" items at near-zero cost
- Reserve LLM evaluation for items where the quality determination is genuinely ambiguous
- Emit a structured report from every gate pass — not just pass/fail counts, but per-item reasons

**Why this matters at scale:**
In a 60-item batch with a 35% pre-filter rejection rate, skipping the cheap gate would cost approximately 21 unnecessary LLM judge calls per run. At 6 dimensions per item, that's 126 unnecessary API calls. The gate doesn't eliminate the LLM judge; it makes the LLM judge's signal cleaner and its cost lower.

---

## 4. Treat Automated LLM Output as Input from an Untrusted Source

Any LLM whose output feeds back into a pipeline is producing input to a downstream system. That downstream system has constraints. Those constraints must be explicitly communicated to the LLM — they cannot be assumed.

**The failure mode to avoid:**
An auto-correction LLM generates a positive example that uses a phrase your quality gate bans. The generator learns the phrase from the positive example and starts producing it at scale. You've introduced the problem you were trying to fix.

**In practice:**
- Before calling an LLM whose output will be processed by downstream validators, inject the validator's constraint list into the LLM's prompt
- Treat the LLM synthesis call like a code review input — verify the output before applying it
- Log what was accepted versus what was edited or rejected

**The generalized principle:**
Any system boundary that accepts external input requires explicit constraint communication. An LLM call whose output feeds back into the system is a trust boundary, even if it's calling your own API key.

---

## 5. Build for Resumability, Not Just Completion

A pipeline that can only run from scratch is fragile by design. For any pipeline with human-in-the-loop steps, external API calls, or wall-clock times measured in tens of minutes, resumability is a correctness requirement, not a convenience feature.

**In practice:**
- Persist state after every completed step in a machine-readable format
- Use that state file to resolve all subsequent filenames — no placeholders, no manual timestamp copy-pasting
- Design pause points to emit exact, copy-paste commands with all variables resolved
- Test resume from every step before the pipeline is "done"

**The test:**
If a pipeline step fails or the process is interrupted, can the pipeline continue from where it stopped without re-doing expensive work? If no, the pipeline isn't production-ready.

---

## 6. Reproducibility Is Not Optional

Every run should produce artifacts that are independently verifiable and traceable to the exact inputs that produced them.

**In practice:**
- Timestamp every output file; embed the generation parameters (provider, model, variant, prompt file) in a `_meta` block alongside the data
- Use variant labels (`iter1_weak`, `iter2_corrected`) that describe the prompt, not just the sequence
- Pin the data schema to a versioned model definition; derive all validation from that definition
- Commit prompt files alongside the code that uses them

**Why this matters:**
When a run produces unexpected results, you need to be able to re-run it exactly. If the prompt that produced the output isn't tracked, or the provider isn't recorded, you can't reproduce the failure or verify the fix.

---

## 7. Preserve Failure History in Durable Artifacts

Failure analysis requires failure data. If failure reasons exist only in memory, a terminal session, or informal notes, they cannot be retrieved for systematic analysis.

**In practice:**
- Capture human labeling failure reasons in a structured, machine-readable format at the time of labeling
- Embed failure notes in git commit messages with a parseable header (`Failure notes:`)
- Use the commit history as a searchable failure log: `git log --format="%B" | grep "FAIL —"`
- Build tooling that reads failure history from the commit store; don't build a separate notes system

**What this enables:**
When generating improved rubric criteria or prompt additions, the synthesis LLM can be given all failure notes from all previous runs, not just the most recent session. The failure history accumulates rather than being lost between sessions.

---

## 8. Make the Iteration Loop Fast Enough to Run

A correction loop that takes 2.5 hours per iteration will be run fewer times than one that takes 30 minutes. Iteration speed directly constrains how much learning you can extract from a feedback loop.

**In practice:**
- Identify which steps dominate wall-clock time and optimize them first (typically: generation and judge evaluation)
- Quantify the tradeoff between model quality and time per run before committing to a provider for bulk work
- Smoke-test configurations at small scale (5–15 items) before committing to full runs
- Separate the fast automated steps from the slow human steps; run the fast ones in sequence, schedule the slow one once per loop

**The provider time table (reference):**

| Generator / Judge | Estimated Step 1 (60 items) | Estimated Step 4 (360 judge calls) |
|---|---|---|
| Groq free tier / Groq free tier | ~18 min | ~22 min |
| Groq free tier / OpenAI gpt-4o-mini | ~18 min | ~5 min |
| OpenAI gpt-4o-mini / OpenAI gpt-4o-mini | ~4 min | ~5 min |

---

## 9. Provider Independence

AI systems should not require a specific inference provider to function. Rate limits, model deprecations, pricing changes, and availability incidents all create operational pressure to switch providers. That pressure should be absorbable at one configuration boundary, not scattered across the codebase.

**In practice:**
- Resolve provider identity at initialization; pass a uniform client object downstream
- Use env vars for provider and model selection; no hardcoded provider strings outside the provider-resolution layer
- Test the critical path on at least two providers before declaring the system "done"
- Document provider-specific behaviors (rate limits, token constraints, output characteristics) where they affect pipeline decisions

**What provider independence doesn't guarantee:**
Behavior parity across providers. A pipeline that produces 9.4% failure rate with one model may produce 1.1% failure rate with another. Provider independence abstracts the API layer; it doesn't abstract model capability. Measurement comparisons must control for model identity.

---

## 10. Cost Visibility

AI API calls have real costs. Pipeline design decisions — batch size, model selection, retry behavior, judge call count — directly affect spend. Build with awareness of the cost model.

**In practice:**
- Choose the cheapest model that meets the accuracy requirement for each component (expensive for judges; cheap acceptable for generators in baseline runs)
- Add explicit cost estimates to pipeline documentation (tokens per call × calls per run × price per token)
- For free-tier providers, factor in rate limit delays as a cost measured in wall-clock time, not API spend
- Pre-filter with cheap gates to reduce expensive judge call volume

**The tradeoff to document:**
Switching to a paid provider for the generator reduces rate-limit delays but may reduce baseline failure rates, potentially confounding improvement measurements. This tradeoff should be made explicitly and documented when it occurs.

---

## 11. Human Verification at Calibration Points

Automated systems can optimize confidently in the wrong direction if they're never checked against human judgment. The calibration points in a pipeline are where human verification ensures the automated system is measuring what you intend to measure.

**In practice:**
- Establish at least one calibration point where human judgments are collected and compared to automated judgments before automated metrics drive decisions
- The calibration sample doesn't need to be large — 20 items across 6 dimensions is sufficient to identify systematic disagreement
- When automated and human judgments disagree systematically, fix the automated system before using it to drive iteration
- Document the calibration result and the threshold used; revisit if the evaluation rubric changes

---

## 12. Measurement Must Be Controlled

When multiple variables change between measurement points, the measurement is confounded. Improvement attributable to a prompt change looks different from improvement attributable to a model change. Both look like the same number.

**In practice:**
- Hold the evaluation model constant when comparing generator prompt variants
- Hold the generation model constant when comparing judge rubric variants
- When a model switch is unavoidable mid-experiment, document it explicitly and note that the measurement is confounded
- A controlled experiment that isolates one variable produces one measurement; an uncontrolled experiment that changes three variables produces noise

**The honest failure mode:**
This project's iter3 results (1.1% failure rate) reflect both the prompt correction and a generator model upgrade. The 88.3% improvement claim is accurate as measured; its attribution to the prompt change alone is overstated. Documenting this explicitly is part of honest engineering practice.

---

*← [README](README.md) · [Architecture](ARCHITECTURE.md) · [Design Decisions](DESIGN_DECISIONS.md)*
