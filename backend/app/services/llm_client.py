import json
import os
import re


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise LLMError(f"Could not parse JSON from LLM response: {text[:200]!r}")


def _call_groq(system: str, user: str) -> dict:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise LLMError("GROQ_API_KEY is not set")

    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return _extract_json(resp.choices[0].message.content)


def _call_anthropic(system: str, user: str) -> dict:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _extract_json(resp.content[0].text)


_PROVIDERS = {
    "groq": _call_groq,
    "anthropic": _call_anthropic,
}


def complete_json(system: str, user: str) -> dict:
    """Send a system+user prompt to whichever provider is configured via
    LLM_PROVIDER and return the parsed JSON response. Swapping providers is a
    one-line env change; no call sites need to know which one is active."""

    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    handler = _PROVIDERS.get(provider)
    if handler is None:
        raise LLMError(f"Unknown LLM_PROVIDER '{provider}', expected one of {list(_PROVIDERS)}")

    return handler(system, user)
