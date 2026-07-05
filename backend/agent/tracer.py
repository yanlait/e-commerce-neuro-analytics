from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

_lf = Langfuse()


def trace_query(
    question: str,
    sql: str | None,
    result: list[dict] | None,
    latency_ms: float,
    chunks: list[dict] | None = None,
    llm_meta: dict | None = None,
):
    trace = _lf.trace(name="analytics-query", input={"question": question})

    if chunks:
        trace.span(
            name="rag-retrieval",
            input={"query": question},
            output={"chunks": [{"source": c["source"], "text": c["text"][:200]} for c in chunks]},
        )

    if sql:
        # generation span carries model + token usage so Langfuse computes cost
        gen_kwargs = {"name": "sql-generation", "input": {"question": question}, "output": {"sql": sql}}
        if llm_meta:
            gen_kwargs["model"] = llm_meta.get("model")
            gen_kwargs["usage_details"] = {
                "input": llm_meta.get("input_tokens", 0),
                "output": llm_meta.get("output_tokens", 0),
            }
            gen_kwargs["cost_details"] = {"total": llm_meta.get("cost_usd", 0.0)}
            gen_kwargs["metadata"] = {
                "provider": llm_meta.get("provider"),
                "llm_latency_ms": llm_meta.get("latency_ms"),
            }
        trace.generation(**gen_kwargs)

        trace.span(
            name="sql-execution",
            input={"sql": sql},
            output={"rows": len(result or []), "preview": (result or [])[:3]},
            metadata={"latency_ms": round(latency_ms, 2)},
        )

    trace_meta = {"answer_type": "sql" if sql else "rag"}
    if llm_meta:
        trace_meta["model"] = llm_meta.get("model")
        trace_meta["provider"] = llm_meta.get("provider")
    trace.update(output={"rows": len(result or []), **trace_meta})
    _lf.flush()
    return trace.id
