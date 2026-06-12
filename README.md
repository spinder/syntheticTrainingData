# syntheticTrainingData
A training project.

## Setup

Install the dependencies:
```bash
pip install datasets huggingface_hub pydantic jsonschema pandas pyarrow
```

Generate and validate the schema:
```bash
python generate_json_schema.py
python validate_schema_self_check.py
# NOTE: HF API key required for dataset validation:
# python validate_hf_dataset.py
```

## Generating Training Data

`generate.py` produces Home DIY Repair Q&A items in JSONL format using your chosen
LLM provider. The default run generates **60 items** (12 per category × 5 categories),
satisfying the ≥50 target.

Output is written to `generated_data/<variant>_<timestamp>.jsonl`.

### Quick start

```bash
# 60 items with Groq (free, no local GPU required)
export GROQ_API_KEY="gsk_..."
python3 generate.py --provider groq --model llama-3.1-8b-instant

# 60 items with Claude (highest quality)
export ANTHROPIC_API_KEY="sk-ant-..."
python3 generate.py --provider claude

# 60 items with OpenAI
export OPENAI_API_KEY="sk-..."
python3 generate.py --provider openai --model gpt-4o-mini

# 60 items with DeepSeek
export DEEPSEEK_API_KEY="sk-..."
python3 generate.py --provider deepseek
```

### Controlling item count

```bash
# 50 items — 10 per category
python3 generate.py --provider groq --model llama-3.1-8b-instant --per-category 10

# 60 items — 12 per category (default)
python3 generate.py --provider groq --model llama-3.1-8b-instant

# Quick smoke test — 15 items total (3 per category)
python3 generate.py --provider groq --model llama-3.1-8b-instant --per-category 3
```

### Labelling a run

```bash
# Tag the output file with a variant name (e.g. after a prompt change)
python3 generate.py --provider groq --variant corrected_v2
```

### Ollama (local)

> **WARNING:** Ollama runs the model entirely on your local machine. Insufficient
> RAM or VRAM **will crash your system.** See the hardware table in the
> [LLM Judge Providers](#llm-judge-providers) section before proceeding.
> Use `groq` instead if you are unsure.

```bash
# Pull the model first, then generate
ollama pull llama3.1
python3 generate.py --provider ollama --model llama3.1

# Custom Ollama host
OLLAMA_BASE_URL=http://192.168.1.10:11434 python3 generate.py --provider ollama --model llama3.1
```

---

## LLM Judge Providers

The `llm/` evaluation pipeline supports multiple inference backends. Set `LLM_PROVIDER`
and the matching key before running `promptfoo eval --config llm/promptfooconfig.yaml`.

| Provider | Default model | Key env var | Notes |
|---|---|---|---|
| `claude` | claude-opus-4-7 | `ANTHROPIC_API_KEY` | Highest quality |
| `openai` | gpt-4o | `OPENAI_API_KEY` | |
| `deepseek` | deepseek-chat | `DEEPSEEK_API_KEY` | Cost-effective |
| `groq` | llama-3.1-8b-instant | `GROQ_API_KEY` | **Recommended for fast/free cloud inference** |
| `ollama` | llama3.2 | *(none)* | Local only — see hardware warning below |

### Groq (recommended free option)

Groq runs Llama, Mixtral, and Gemma models in the cloud with no local GPU required:

```bash
export LLM_PROVIDER=groq
export GROQ_API_KEY="gsk_..."          # free key at console.groq.com
export LLM_MODEL=llama-3.1-8b-instant  # or llama3-70b-8192, mixtral-8x7b-32768
promptfoo eval --config llm/promptfooconfig.yaml
```

### Ollama — Local Inference

> **WARNING:** Ollama runs the full model on your local machine. Running a model that
> exceeds your available RAM or VRAM **will crash your system.** Verify your hardware
> before use. Use `groq` instead if you are unsure.

**Minimum hardware requirements by model size:**

| Model size | RAM | VRAM (GPU) |
|---|---|---|
| ~3B (e.g. `phi3:mini`, `llama3.2:1b`) | 8 GB | 6 GB |
| ~7B (e.g. `llama3.2`, `mistral`) | 16 GB | 8 GB |
| ~13B | 32 GB | 16 GB |
| ~70B | 64 GB | 48 GB (multi-GPU) |

If your machine meets the requirements, start the Ollama server and then run:

```bash
ollama pull phi3:mini                   # pull the model first
export LLM_PROVIDER=ollama
export LLM_MODEL=phi3:mini             # use the lightest model that fits your hardware
# Optional: export OLLAMA_HOST=http://localhost:11434  (default)
promptfoo eval --config llm/promptfooconfig.yaml
```

