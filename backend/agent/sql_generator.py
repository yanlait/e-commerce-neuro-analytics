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
# local fallback so the system works when Langfuse is unreachable (CI, outages)
_FALLBACK_PROMPT = (Path(__file__).parent / "prompts/sql_generator.txt").read_text()


def _get_system_prompt() -> str:
    schema_yaml = yaml.dump(_schema["tables"], allow_unicode=True)
    try:
        prompt = _lf.get_prompt("sql-generator", label="latest")
        compiled = prompt.compile(schema=schema_yaml)
        return compiled if isinstance(compiled, str) else compiled[0]["content"]
    except Exception:
        return _FALLBACK_PROMPT.replace("{{schema}}", schema_yaml)


def generate_sql(
    question: str,
    history: list[dict] | None = None,
    context_chunks: list[dict] | None = None,
    repair: dict | None = None,
) -> dict:
    """
    context_chunks: retrieved metric definitions / schema hints injected into the prompt.
    repair: {"sql": <bad sql>, "error": <db error>} — asks the model to fix a failed query.
    """
    system = _get_system_prompt()

    # inject retrieved context so metric definitions inform generation
    if context_chunks:
        ctx = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in context_chunks[:3])
        system += (
            "\n\nRelevant documentation (use these definitions to pick the correct "
            f"tables/columns and metric formulas):\n{ctx}"
        )

    messages = [{"role": "system", "content": system}]
    if history:
        messages += history

    user_content = question
    if repair:
        user_content = (
            f"{question}\n\nYour previous SQL failed:\n{repair['sql']}\n\n"
            f"Error:\n{repair['error']}\n\nReturn corrected SQL in the same JSON format."
        )
    messages.append({"role": "user", "content": user_content})

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
