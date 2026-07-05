"""
Unified LLM interface with swappable providers.
Controlled by env var LLM_PROVIDER (ollama | openai | anthropic).

Returns text + usage metadata (latency, tokens) for cost/latency tracking.
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# model per provider (override with LLM_MODEL)
_DEFAULT_MODEL = {
    "ollama": "gpt-oss:20b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}

# approx USD per 1M tokens (input, output) — for cost estimation
_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "gpt-oss:20b": (0.0, 0.0),  # local, free
}


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "ollama")


def _model() -> str:
    return os.environ.get("LLM_MODEL", _DEFAULT_MODEL.get(_provider(), "gpt-oss:20b"))


def _estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = _PRICING.get(model, (0.0, 0.0))
    return round(in_tok / 1e6 * pin + out_tok / 1e6 * pout, 6)


def chat(messages: list[dict], temperature: float = 0.0) -> dict:
    """Returns {text, latency_ms, input_tokens, output_tokens, cost_usd, model, provider}."""
    model = _model()
    t0 = time.monotonic()

    provider = _provider()
    if provider == "ollama":
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": model, "messages": messages, "stream": False,
                  "options": {"temperature": temperature}},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["message"]["content"].strip()
        in_tok = data.get("prompt_eval_count", 0)
        out_tok = data.get("eval_count", 0)

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=temperature,
        )
        text = resp.choices[0].message.content.strip()
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        chat_msgs = [m for m in messages if m["role"] != "system"]
        resp = client.messages.create(
            model=model, max_tokens=1024, system=system,
            messages=chat_msgs, temperature=temperature,
        )
        text = resp.content[0].text.strip()
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    return {
        "text": text,
        "latency_ms": latency_ms,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": _estimate_cost(model, in_tok, out_tok),
        "model": model,
        "provider": provider,
    }
