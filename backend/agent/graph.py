"""
LangGraph multi-agent orchestration for the analytics assistant.

Mature graph with retrieval-before-generation, a generate→validate→repair loop,
and output grounding. Each node maps to a distinct quality dimension.

    START
      │
      ▼
  input_guardrail   intent / injection safety      → reject
      ▼
  retrieve          fetch metric defs + context (feeds generation)
      ▼
  planner           tool selection: sql vs rag     → rag_answer
      ▼
  sql_generate      SQL from schema + retrieved defs
      ▼
  sql_validate      guardrails + EXPLAIN dry-run
      │   ├─ invalid & tries<MAX → repair → sql_validate   ⟲
      │   └─ exhausted → graceful_fail
      ▼
  execute           run SQL; empty → rag_enrich
      ▼
  verify_grounding  cheap faithfulness check
      ▼
     END

Reuses the same underlying functions as planner.py; control flow is explicit
and every transition is observable.
"""
import re
import time
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END

from .classifier import is_analytics_question
from .router import decide_route
from .sql_generator import generate_sql
from .sql_runner import run_sql, validate_sql, GuardrailError
from .tracer import trace_query
from .query_log import log
from ..rag.retriever import retrieve

MAX_REPAIRS = 2

NOT_ANALYTICS_REPLY = (
    "Привет! Я аналитический ассистент по e-commerce данным Olist.\n\n"
    "Задай вопрос про данные, например:\n"
    "• Top 5 product categories by revenue\n"
    "• Average review score by state\n"
    "• Monthly revenue in 2017\n"
    "• What is LTV?"
)


class State(TypedDict, total=False):
    question: str
    history: list
    route: str
    chunks: list
    sql: str | None
    explanation: str
    validation_error: str | None
    repair_attempts: int
    data: list | None
    answer_type: str
    message: str
    grounding_ok: bool
    # accumulated across all LLM calls in this run
    model: str | None
    provider: str | None
    cost_usd: float
    input_tokens: int
    output_tokens: int
    llm_latency_ms: float
    sql_latency_ms: float


def _accumulate(state: State, meta: dict):
    state["cost_usd"] = state.get("cost_usd", 0.0) + (meta.get("cost_usd") or 0.0)
    state["input_tokens"] = state.get("input_tokens", 0) + (meta.get("input_tokens") or 0)
    state["output_tokens"] = state.get("output_tokens", 0) + (meta.get("output_tokens") or 0)
    state["llm_latency_ms"] = state.get("llm_latency_ms", 0.0) + (meta.get("latency_ms") or 0.0)
    if meta.get("model"):
        state["model"] = meta["model"]
    if meta.get("provider"):
        state["provider"] = meta["provider"]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def input_guardrail_node(state: State) -> State:
    state["repair_attempts"] = 0
    state["cost_usd"] = 0.0
    state["route"] = "continue" if is_analytics_question(state["question"]) else "reject"
    return state


def reject_node(state: State) -> State:
    state.update(answer_type="rejected", message=NOT_ANALYTICS_REPLY, data=None, chunks=[])
    return state


def retrieve_node(state: State) -> State:
    state["chunks"] = retrieve(state["question"])
    return state


def planner_node(state: State) -> State:
    decision = decide_route(state["question"], state.get("chunks"))
    _accumulate(state, decision)
    state["route"] = decision["route"]  # "sql" | "rag"
    return state


def sql_generate_node(state: State) -> State:
    generated = generate_sql(
        state["question"],
        history=state.get("history") or [],
        context_chunks=state.get("chunks"),
    )
    _accumulate(state, {
        "cost_usd": generated.get("llm_cost_usd"),
        "input_tokens": generated.get("input_tokens"),
        "output_tokens": generated.get("output_tokens"),
        "latency_ms": generated.get("llm_latency_ms"),
        "model": generated.get("llm_model"),
        "provider": generated.get("llm_provider"),
    })
    state["sql"] = generated["sql"]
    state["explanation"] = generated["explanation"]
    return state


def sql_validate_node(state: State) -> State:
    if not state.get("sql"):
        state["validation_error"] = "no SQL produced"
        return state
    ok, err = validate_sql(state["sql"])
    state["validation_error"] = None if ok else err
    return state


def repair_node(state: State) -> State:
    state["repair_attempts"] = state.get("repair_attempts", 0) + 1
    generated = generate_sql(
        state["question"],
        history=state.get("history") or [],
        context_chunks=state.get("chunks"),
        repair={"sql": state["sql"], "error": state["validation_error"]},
    )
    _accumulate(state, {
        "cost_usd": generated.get("llm_cost_usd"),
        "input_tokens": generated.get("input_tokens"),
        "output_tokens": generated.get("output_tokens"),
        "latency_ms": generated.get("llm_latency_ms"),
        "model": generated.get("llm_model"),
        "provider": generated.get("llm_provider"),
    })
    state["sql"] = generated["sql"]
    state["explanation"] = generated["explanation"]
    return state


def execute_node(state: State) -> State:
    t0 = time.monotonic()
    try:
        result = run_sql(state["sql"])
        state["sql_latency_ms"] = (time.monotonic() - t0) * 1000
        all_none = all(
            v is None or (isinstance(v, float) and v != v)
            for row in result for v in row.values()
        )
        state["data"] = result
        if not result or all_none:
            state["route"] = "empty"
        else:
            state["answer_type"] = "sql"
            state["route"] = "ok"
    except GuardrailError as e:
        state["sql_latency_ms"] = (time.monotonic() - t0) * 1000
        state.update(data=None, answer_type="blocked",
                     explanation=f"Blocked for security: {e}", chunks=[], route="ok")
    return state


def graceful_fail_node(state: State) -> State:
    state.update(
        answer_type="failed", data=None,
        explanation=f"Could not produce valid SQL after {MAX_REPAIRS} repair attempts. "
                    f"Last error: {state.get('validation_error')}",
    )
    return state


def rag_answer_node(state: State) -> State:
    """Definitional questions — chunks already retrieved."""
    if not state.get("chunks"):
        state["chunks"] = retrieve(state["question"])
    state["answer_type"] = "rag"
    return state


def rag_enrich_node(state: State) -> State:
    """SQL ran but empty — enrich with dataset-period/context docs."""
    state["chunks"] = retrieve(state["question"] + " date range dataset period")
    state["answer_type"] = "sql"  # SQL did run, just empty
    return state


def verify_grounding_node(state: State) -> State:
    """Cheap deterministic faithfulness check: numbers cited in the explanation
    should appear in the returned data. Flags potential hallucination without an LLM call."""
    explanation = state.get("explanation") or ""
    data = state.get("data") or []
    nums_in_expl = set(re.findall(r"\d[\d,\.]*", explanation.replace(",", "")))
    if not nums_in_expl or not data:
        state["grounding_ok"] = True
        return state
    data_str = str(data)
    grounded = any(n in data_str.replace(",", "") for n in nums_in_expl)
    state["grounding_ok"] = grounded
    return state


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def after_guardrail(state: State) -> Literal["reject", "retrieve"]:
    return "reject" if state["route"] == "reject" else "retrieve"


def after_planner(state: State) -> Literal["sql_generate", "rag_answer"]:
    return "sql_generate" if state["route"] == "sql" else "rag_answer"


def after_validate(state: State) -> Literal["execute", "repair", "graceful_fail"]:
    if state.get("validation_error") is None:
        return "execute"
    if state.get("repair_attempts", 0) < MAX_REPAIRS:
        return "repair"
    return "graceful_fail"


def after_execute(state: State) -> Literal["rag_enrich", "verify_grounding"]:
    return "rag_enrich" if state.get("route") == "empty" else "verify_grounding"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph():
    g = StateGraph(State)
    g.add_node("input_guardrail", input_guardrail_node)
    g.add_node("reject", reject_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("planner", planner_node)
    g.add_node("sql_generate", sql_generate_node)
    g.add_node("sql_validate", sql_validate_node)
    g.add_node("repair", repair_node)
    g.add_node("execute", execute_node)
    g.add_node("graceful_fail", graceful_fail_node)
    g.add_node("rag_answer", rag_answer_node)
    g.add_node("rag_enrich", rag_enrich_node)
    g.add_node("verify_grounding", verify_grounding_node)

    g.set_entry_point("input_guardrail")
    g.add_conditional_edges("input_guardrail", after_guardrail,
                            {"reject": "reject", "retrieve": "retrieve"})
    g.add_edge("retrieve", "planner")
    g.add_conditional_edges("planner", after_planner,
                            {"sql_generate": "sql_generate", "rag_answer": "rag_answer"})
    g.add_edge("sql_generate", "sql_validate")
    g.add_conditional_edges("sql_validate", after_validate,
                            {"execute": "execute", "repair": "repair", "graceful_fail": "graceful_fail"})
    g.add_edge("repair", "sql_validate")
    g.add_conditional_edges("execute", after_execute,
                            {"rag_enrich": "rag_enrich", "verify_grounding": "verify_grounding"})
    g.add_edge("reject", END)
    g.add_edge("rag_answer", END)
    g.add_edge("rag_enrich", END)
    g.add_edge("graceful_fail", END)
    g.add_edge("verify_grounding", END)
    return g.compile()


_graph = build_graph()


# ---------------------------------------------------------------------------
# Public API — same shape as planner.answer()
# ---------------------------------------------------------------------------

def answer(question: str, history: list[dict] | None = None) -> dict:
    final = _graph.invoke({"question": question, "history": history or []})

    answer_type = final.get("answer_type", "rag")
    meta = {
        "model": final.get("model"),
        "provider": final.get("provider"),
        "cost_usd": round(final.get("cost_usd", 0.0), 6),
        "input_tokens": final.get("input_tokens", 0),
        "output_tokens": final.get("output_tokens", 0),
        "latency_ms": round(final.get("llm_latency_ms", 0.0), 1),
    }

    trace_id = None
    if answer_type in ("sql", "rag"):
        trace_id = trace_query(
            question, final.get("sql"), final.get("data"),
            final.get("sql_latency_ms", 0), chunks=final.get("chunks"),
            llm_meta=meta,
        )
    log(question, final.get("sql"), len(final.get("data") or []),
        final.get("sql_latency_ms", 0), answer_type=answer_type,
        error=final.get("validation_error") if answer_type == "failed" else (
            final.get("explanation") if answer_type == "blocked" else None),
        model=meta["model"], cost_usd=meta["cost_usd"],
        input_tokens=meta["input_tokens"], output_tokens=meta["output_tokens"],
        llm_latency_ms=meta["latency_ms"])

    return {
        "sql": final.get("sql"),
        "data": final.get("data"),
        "chunks": final.get("chunks", []),
        "explanation": final.get("explanation", ""),
        "answer_type": answer_type,
        "message": final.get("message"),
        "grounding_ok": final.get("grounding_ok", True),
        "repair_attempts": final.get("repair_attempts", 0),
        "trace_id": trace_id,
        **meta,
    }
