import json
import yaml
from pathlib import Path
from dotenv import load_dotenv
from langfuse import Langfuse
from .llm import chat

load_dotenv()

_lf = Langfuse()
_schema = yaml.safe_load(
    (Path(__file__).parent.parent / "semantic_layer/metrics.yaml").read_text()
)


def generate_sql(question: str, history: list[dict] | None = None) -> dict:
    prompt = _lf.get_prompt("sql-generator", label="latest")
    compiled = prompt.compile(schema=yaml.dump(_schema["tables"], allow_unicode=True))

    system = compiled if isinstance(compiled, str) else compiled[0]["content"]
    messages = [{"role": "system", "content": system}]
    if history:
        messages += history
    messages.append({"role": "user", "content": question})

    result = chat(messages)
    raw = result["text"]

    # strip markdown code blocks if model adds them
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
        sql = parsed.get("sql", "").strip()
        explanation = parsed.get("explanation", "")
    except json.JSONDecodeError:
        # fallback: treat as plain SQL if model ignores JSON instruction
        sql = raw if raw.upper().startswith(("SELECT", "WITH")) else ""
        explanation = ""

    if not sql.upper().startswith(("SELECT", "WITH")):
        sql = None

    return {
        "sql": sql,
        "explanation": explanation,
        "llm_latency_ms": result["latency_ms"],
        "llm_cost_usd": result["cost_usd"],
        "llm_model": result["model"],
        "llm_provider": result["provider"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }
