"""
Decides which tool to use for a given user question:
  - sql_query  → generate and run DuckDB SQL
  - rag_search → search markdown docs
  - direct     → answer from context alone
"""
import time
from .sql_runner import run_sql
from .sql_generator import generate_sql
from .tracer import trace_query
from .query_log import log
from ..rag.retriever import retrieve


def answer(question: str, history: list[dict]) -> dict:
    chunks = retrieve(question)
    sql = generate_sql(question)

    if not sql:
        trace_id = trace_query(question, None, None, 0, chunks=chunks)
        log(question, None, 0, 0, answer_type="rag")
        return {"sql": None, "data": None, "chunks": chunks, "trace_id": trace_id}

    t0 = time.monotonic()
    try:
        result = run_sql(sql)
        latency_ms = (time.monotonic() - t0) * 1000

        # empty result — enrich with RAG context so user understands why
        all_none = all(v is None or (isinstance(v, float) and v != v) for row in result for v in row.values())
        if not result or all_none:
            chunks = retrieve(question + " date range dataset period")

        trace_id = trace_query(question, sql, result, latency_ms, chunks=chunks)
        log(question, sql, len(result), latency_ms)
        return {"sql": sql, "data": result, "chunks": chunks, "trace_id": trace_id}
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        log(question, sql, 0, latency_ms, error=str(e))
        raise
