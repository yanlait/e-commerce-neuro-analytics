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


def generate_sql(question: str) -> str | None:
    prompt = _lf.get_prompt("sql-generator", label="latest")
    compiled = prompt.compile(schema=yaml.dump(_schema["tables"], allow_unicode=True))

    if isinstance(compiled, str):
        messages = [{"role": "system", "content": compiled}, {"role": "user", "content": question}]
    else:
        messages = compiled + [{"role": "user", "content": question}]

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={"model": "gpt-oss:20b", "messages": messages, "stream": False},
        timeout=60,
    )
    response.raise_for_status()
    sql = response.json()["message"]["content"].strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # model refused or gave explanation instead of SQL
    if not sql.upper().startswith(("SELECT", "WITH")):
        return None
    return sql
