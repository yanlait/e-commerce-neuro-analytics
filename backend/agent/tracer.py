from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

_lf = Langfuse()


def trace_query(question: str, sql: str, result: list[dict], latency_ms: float):
    trace = _lf.trace(name="analytics-query", input={"question": question})
    trace.span(name="sql-generation", input={"question": question}, output={"sql": sql})
    trace.span(
        name="sql-execution",
        input={"sql": sql},
        output={"rows": len(result), "preview": result[:3]},
        metadata={"latency_ms": round(latency_ms, 2)},
    )
    trace.update(output={"rows": len(result)})
    _lf.flush()
