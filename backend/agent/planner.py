import time
from .sql_runner import run_sql
from .sql_generator import generate_sql
from .classifier import is_analytics_question
from .tracer import trace_query
from .query_log import log
from ..rag.retriever import retrieve

NOT_ANALYTICS_REPLY = (
    "Привет! Я аналитический ассистент по e-commerce данным Olist.\n\n"
    "Задай вопрос про данные, например:\n"
    "• Top 5 product categories by revenue\n"
    "• Average review score by state\n"
    "• Monthly revenue in 2017\n"
    "• What is LTV?"
)


def answer(question: str, history: list[dict]) -> dict:
    if not is_analytics_question(question):
        log(question, None, 0, 0, answer_type="rejected")
        return {"sql": None, "data": None, "chunks": [], "trace_id": None, "message": NOT_ANALYTICS_REPLY}

    chunks = retrieve(question)
    generated = generate_sql(question, history=history)
    sql = generated["sql"]
    explanation = generated["explanation"]

    if not sql:
        trace_id = trace_query(question, None, None, 0, chunks=chunks)
        log(question, None, 0, 0, answer_type="rag")
        return {"sql": None, "data": None, "chunks": chunks, "trace_id": trace_id, "explanation": explanation}

    t0 = time.monotonic()
    try:
        result = run_sql(sql)
        latency_ms = (time.monotonic() - t0) * 1000

        all_none = all(v is None or (isinstance(v, float) and v != v) for row in result for v in row.values())
        if not result or all_none:
            chunks = retrieve(question + " date range dataset period")

        trace_id = trace_query(question, sql, result, latency_ms, chunks=chunks)
        log(question, sql, len(result), latency_ms)
        return {"sql": sql, "data": result, "chunks": chunks, "trace_id": trace_id, "explanation": explanation}
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        log(question, sql, 0, latency_ms, error=str(e))
        raise
