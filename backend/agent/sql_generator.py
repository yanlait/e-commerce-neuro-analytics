import json
import yaml
import requests
from pathlib import Path
from dotenv import load_dotenv
from langfuse import Langfuse

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

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={"model": "gpt-oss:20b", "messages": messages, "stream": False},
        timeout=60,
    )
    response.raise_for_status()
    raw = response.json()["message"]["content"].strip()

    # strip markdown code blocks if model adds them
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
        sql = result.get("sql", "").strip()
        explanation = result.get("explanation", "")
    except json.JSONDecodeError:
        # fallback: treat as plain SQL if model ignores JSON instruction
        sql = raw if raw.upper().startswith(("SELECT", "WITH")) else ""
        explanation = ""

    if not sql.upper().startswith(("SELECT", "WITH")):
        sql = None

    return {"sql": sql, "explanation": explanation}
