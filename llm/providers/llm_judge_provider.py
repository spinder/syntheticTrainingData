"""
LLM-as-Judge provider — supports Claude, OpenAI, and DeepSeek.

Setup:
  Set LLM_PROVIDER (claude | openai | deepseek) and the matching API key, then run:
    export LLM_PROVIDER=openai
    export OPENAI_API_KEY="sk-..."
    promptfoo eval --config llm/promptfooconfig.yaml

  Optional: override the model with LLM_MODEL.
    export LLM_MODEL=gpt-4o-mini

Provider defaults:
  claude    → claude-opus-4-7   (requires ANTHROPIC_API_KEY)
  openai    → gpt-4o            (requires OPENAI_API_KEY)
  deepseek  → deepseek-chat     (requires DEEPSEEK_API_KEY)
"""

import os

import anthropic
import openai as openai_lib

_PROVIDER_DEFAULTS = {
    "claude":   "claude-opus-4-7",
    "openai":   "gpt-4o",
    "deepseek": "deepseek-chat",
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

    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{_provider}'. Choose: claude, openai, deepseek"
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
    else:  # openai-compatible (openai, deepseek)
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
