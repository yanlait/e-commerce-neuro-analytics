"""
Planner / tool-selection node.

Given a question (and retrieved context), decide which path answers it best:
  - "sql"  → the question needs numbers computed from the database
  - "rag"  → the question is definitional / conceptual, answer from docs
"""
from .llm import chat

SYSTEM = """You are a routing planner for an analytics assistant over an e-commerce dataset.

Decide how to answer the user's question. Reply with exactly one word:
- SQL — the question asks for numbers, metrics, counts, rankings, trends computed from data
  (e.g. "top categories by revenue", "how many orders", "average delivery time")
- RAG — the question asks for a definition, explanation, or concept, or asks whether
  something exists in the dataset (e.g. "what is LTV", "what does freight_value mean",
  "why did orders spike", "do we have a registration date")

Consider the provided documentation context when deciding."""


def decide_route(question: str, context_chunks: list[dict] | None = None) -> dict:
    context = ""
    if context_chunks:
        context = "\n\nContext:\n" + "\n".join(f"- {c['text'][:150]}" for c in context_chunks[:3])

    result = chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question + context},
    ])
    route = "sql" if result["text"].strip().upper().startswith("SQL") else "rag"
    return {
        "route": route,
        "latency_ms": result["latency_ms"],
        "cost_usd": result["cost_usd"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }
