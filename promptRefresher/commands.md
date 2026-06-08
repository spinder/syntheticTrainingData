# promptfoo Command Reference

All commands are run from the project root unless noted.  
Config files live under `{judge}/promptfooconfig.yaml`.  
Log output is collected via `PROMPTFOO_LOG_DIR` — one timestamped file per run.

---

## Human Judge

```bash
# Run eval
promptfoo eval --config human/promptfooconfig.yaml

# Run eval and save results to a timestamped JSON
PROMPTFOO_LOG_DIR=human/logs promptfoo eval --config human/promptfooconfig.yaml \
  --output human/logs/$(date +%Y-%m-%dT%H-%M-%S)-human-results.json

# Run only tests whose description matches a pattern
promptfoo eval --config human/promptfooconfig.yaml --filter-pattern "q1"

# Open the results UI (starts local web server)
promptfoo view

# Open the UI pointing at a specific output file
promptfoo view human/logs/2026-06-07T15-00-00-human-results.json
```

---

## Automated Judge

```bash
# Run eval
promptfoo eval --config automated/promptfooconfig.yaml

# Run with timestamped log collection
PROMPTFOO_LOG_DIR=automated/logs promptfoo eval --config automated/promptfooconfig.yaml \
  --output automated/logs/$(date +%Y-%m-%dT%H-%M-%S)-automated-results.json

# Filter to a specific question category (e.g. questions prefixed "plumbing")
promptfoo eval --config automated/promptfooconfig.yaml --filter-pattern "plumbing"

promptfoo view
```

---

## LLM Judge

```bash
# Run eval (uses Claude as the evaluator via llm-rubric assertions)
promptfoo eval --config llm/promptfooconfig.yaml

# Run with timestamped log collection
PROMPTFOO_LOG_DIR=llm/logs promptfoo eval --config llm/promptfooconfig.yaml \
  --output llm/logs/$(date +%Y-%m-%dT%H-%M-%S)-llm-results.json

# Filter to a subcategory (e.g. a second-level label in the test description)
promptfoo eval --config llm/promptfooconfig.yaml --filter-pattern "safety"

promptfoo view
```

---

## Cross-Judge / All Runs

```bash
# Compare two result files side-by-side in the UI
promptfoo view human/logs/run-A.json automated/logs/run-B.json

# List all cached eval runs (default ~/.promptfoo/results)
promptfoo list evals
```

---

## Timestamp Log Collection

Set `PROMPTFOO_LOG_DIR` to a directory before running `promptfoo eval`.  
promptfoo writes two files per run:
- `promptfoo-debug-<ISO-timestamp>.log`  — full trace
- `promptfoo-error-<ISO-timestamp>.log`  — errors only

```bash
# Human judge with logs going to human/logs/
PROMPTFOO_LOG_DIR=human/logs promptfoo eval --config human/promptfooconfig.yaml
```

---

## Second-Level Category in Prompts

Add a `category` var to each test case and reference it in the prompt template.  
The `--filter-pattern` flag matches against the test's `description` field.

**In `promptfooconfig.yaml`:**
```yaml
tests:
  - description: "plumbing | leaking_pipe"
    vars:
      category: plumbing
      subcategory: leaking_pipe
      question: file://questions/plumbing/leaking_pipe_q1.txt
    assert:
      - type: llm-rubric
        value: "Correct for a leaking pipe repair scenario."

  - description: "electrical | circuit_breaker"
    vars:
      category: electrical
      subcategory: circuit_breaker
      question: file://questions/electrical/circuit_breaker_q1.txt
    assert:
      - type: llm-rubric
        value: "Correct circuit breaker troubleshooting advice."
```

**Filter by second-level category at runtime:**
```bash
# Run only electrical tests
promptfoo eval --config llm/promptfooconfig.yaml --filter-pattern "electrical"

# Run only leaking_pipe tests
promptfoo eval --config llm/promptfooconfig.yaml --filter-pattern "leaking_pipe"
```

**Organize questions under subcategory folders:**
```
llm/questions/
  plumbing/
    leaking_pipe_q1.txt
  electrical/
    circuit_breaker_q1.txt
```

---

## Schema Validation (non-promptfoo)

```bash
# Validate a single JSON record
python3 validate_record.py tests/row.json
python3 validate_record.py tests/bad_row.json

# Self-check the schema file
python3 validate_schema_self_check.py

# Regenerate schema from Pydantic model
python3 generate_json_schema.py

# Validate the HuggingFace dataset
python3 validate_hf_dataset.py
```
