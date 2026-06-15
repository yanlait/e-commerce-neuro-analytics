from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

_lf = Langfuse()


def trace_query(question: str, sql: str | None, result: list[dict] | None, latency_ms: float, chunks: list[dict] | None = None):
    trace = _lf.trace(name="analytics-query", input={"question": question})

    if chunks:
        trace.span(
            name="rag-retrieval",
            input={"query": question},
            output={"chunks": [{"source": c["source"], "text": c["text"][:200]} for c in chunks]},
        )

    if sql:
        trace.span(name="sql-generation", input={"question": question}, output={"sql": sql})
        trace.span(
            name="sql-execution",
            input={"sql": sql},
            output={"rows": len(result or []), "preview": (result or [])[:3]},
            metadata={"latency_ms": round(latency_ms, 2)},
        )

    trace.update(output={"rows": len(result or []), "answer_type": "sql" if sql else "rag"})
    _lf.flush()
    return trace.id
