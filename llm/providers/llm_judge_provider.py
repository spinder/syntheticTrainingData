"""
LLM-as-Judge provider — supports Claude, OpenAI, DeepSeek, Groq, and Ollama (local).

Setup:
  Set LLM_PROVIDER and the matching API key, then run:
    export LLM_PROVIDER=groq
    export GROQ_API_KEY="gsk_..."
    promptfoo eval --config llm/promptfooconfig.yaml

  Optional: override the model with LLM_MODEL.
    export LLM_MODEL=llama-3.1-70b-versatile

Provider defaults:
  claude    → claude-opus-4-7        (requires ANTHROPIC_API_KEY)
  openai    → gpt-4o                 (requires OPENAI_API_KEY)
  deepseek  → deepseek-chat          (requires DEEPSEEK_API_KEY)
  groq      → llama-3.1-8b-instant   (requires GROQ_API_KEY — free tier at console.groq.com)
                Other fast Groq models: llama3-70b-8192, mixtral-8x7b-32768, gemma2-9b-it

  ollama    → llama3.2               (NO API key — local inference via http://localhost:11434)
    *** WARNING: Ollama runs models entirely on your local machine. ***
    *** Before using this provider, verify you have sufficient resources: ***
    ***   - 3B  model  →  minimum  8 GB RAM / 6 GB VRAM                  ***
    ***   - 7B  model  →  minimum 16 GB RAM / 8 GB VRAM                  ***
    ***   - 13B model  →  minimum 32 GB RAM / 16 GB VRAM                 ***
    ***   - 70B model  →  minimum 64 GB RAM / 48 GB VRAM (multi-GPU)     ***
    *** Running a model your hardware cannot support WILL crash your machine. ***
    *** Use groq instead for free cloud inference on the same model families. ***
    Override the model: export LLM_MODEL=phi3:mini  (lightest option, ~2.3 GB)
"""

import os

import anthropic
import openai as openai_lib

_PROVIDER_DEFAULTS = {
    "claude":   "claude-opus-4-7",
    "openai":   "gpt-4o",
    "deepseek": "deepseek-chat",
    "groq":     "llama-3.1-8b-instant",
    "ollama":   "llama3.2",
}

_client   = None
_provider = None
_model    = None


def _init():
    global _client, _provider, _model
    if _client is not None:
        return

    _provider = os.environ.get("LLM_PROVIDER", "claude").lower()
    _model    = os.environ.get("LLM_MODEL") or _PROVIDER_DEFAULTS.get(_provider)

    if _provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it or switch provider: export LLM_PROVIDER=openai"
            )
        _client = anthropic.Anthropic(api_key=key)

    elif _provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Export it: export OPENAI_API_KEY='sk-...'"
            )
        _client = openai_lib.OpenAI(api_key=key)

    elif _provider == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. "
                "Export it: export DEEPSEEK_API_KEY='sk-...'"
            )
        _client = openai_lib.OpenAI(api_key=key, base_url="https://api.deepseek.com/v1")

    elif _provider == "groq":
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com, then: export GROQ_API_KEY='gsk_...'"
            )
        _client = openai_lib.OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")

    elif _provider == "ollama":
        # WARNING: Ollama runs inference locally. Ensure your machine has enough
        # RAM/VRAM for the chosen model before proceeding — see module docstring.
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        _client = openai_lib.OpenAI(api_key="ollama", base_url=f"{ollama_host}/v1")

    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{_provider}'. Choose: claude, openai, deepseek, groq, ollama"
        )


def call_api(prompt, options, context):
    _init()

    if _provider == "claude":
        msg = _client.messages.create(
            model=_model,
            max_tokens=16,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip().lower()
    else:  # openai-compatible (openai, deepseek, groq, ollama)
        resp = _client.chat.completions.create(
            model=_model,
            max_tokens=16,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip().lower()

    if raw.startswith("pass"):
        verdict = "pass"
    elif raw.startswith("fail"):
        verdict = "fail"
    else:
        if "pass" in raw and "fail" not in raw:
            verdict = "pass"
        elif "fail" in raw and "pass" not in raw:
            verdict = "fail"
        else:
            verdict = raw  # surface unexpected output for inspection

    return {"output": verdict}
