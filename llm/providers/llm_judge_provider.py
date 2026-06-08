"""
LLM-as-Judge provider using Claude.

Setup:
  1. Get your Anthropic API key at https://console.anthropic.com/settings/keys
  2. Export it before running promptfoo:
       export ANTHROPIC_API_KEY="sk-ant-..."
  3. Run:
       ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY promptfoo eval --config llm/promptfooconfig.yaml
"""

import os
import anthropic

_client = None

def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Export it before running: export ANTHROPIC_API_KEY='sk-ant-...'"
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def call_api(prompt, options, context):
    client = _get_client()

    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=16,
        temperature=0,  # deterministic — judge must be consistent
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().lower()

    if raw.startswith("pass"):
        verdict = "pass"
    elif raw.startswith("fail"):
        verdict = "fail"
    else:
        # Fallback: search for the word anywhere in the response
        if "pass" in raw and "fail" not in raw:
            verdict = "pass"
        elif "fail" in raw and "pass" not in raw:
            verdict = "fail"
        else:
            verdict = raw  # surface unexpected output for inspection

    return {"output": verdict}
