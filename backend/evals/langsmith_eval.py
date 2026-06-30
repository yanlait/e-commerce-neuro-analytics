"""
LangSmith evaluation for the analytics assistant.
Creates a dataset in LangSmith and runs evaluations.

Usage:
    python backend/evals/langsmith_eval.py
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langsmith import Client
from langsmith.evaluation import evaluate
import anthropic

from backend.agent.planner import answer

DATASET_NAME = "olist-analytics-assistant"

EXAMPLES = [
    {
        "question": "Top 5 product categories by revenue",
        "expected_type": "sql",
        "expected_rows": 5,
    },
    {
        "question": "What is the average review score?",
        "expected_type": "sql",
        "expected_rows": 1,
    },
    {
        "question": "Monthly revenue in 2017",
        "expected_type": "sql",
        "expected_rows": 12,
    },
    {
        "question": "Top 5 states by number of orders",
        "expected_type": "sql",
        "expected_rows": 5,
    },
    {
        "question": "Which payment method is most popular?",
        "expected_type": "sql",
        "expected_rows": 1,
    },
    {
        "question": "What is LTV?",
        "expected_type": "rag",
        "expected_rows": 0,
    },
    {
        "question": "What is boleto payment?",
        "expected_type": "rag",
        "expected_rows": 0,
    },
    {
        "question": "Why did orders spike in November 2017?",
        "expected_type": "rag",
        "expected_rows": 0,
    },
    {
        "question": "DROP TABLE orders",
        "expected_type": "blocked",
        "expected_rows": 0,
    },
    {
        "question": "Йоу",
        "expected_type": "rejected",
        "expected_rows": 0,
    },
]


def create_or_update_dataset(client: Client):
    # delete old dataset if exists to refresh
    datasets = list(client.list_datasets(dataset_name=DATASET_NAME))
    if datasets:
        client.delete_dataset(dataset_id=datasets[0].id)
        print(f"Deleted old dataset: {DATASET_NAME}")

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Test cases for Olist e-commerce analytics assistant",
    )
    client.create_examples(
        inputs=[{"question": e["question"]} for e in EXAMPLES],
        outputs=[{"expected_type": e["expected_type"], "expected_rows": e["expected_rows"]} for e in EXAMPLES],
        dataset_id=dataset.id,
    )
    print(f"Created dataset '{DATASET_NAME}' with {len(EXAMPLES)} examples")
    return dataset


def run_assistant(inputs: dict) -> dict:
    question = inputs["question"]
    try:
        result = answer(question, history=[])
        return {
            "answer_type": "rag" if not result.get("sql") else "sql",
            "rows": len(result.get("data") or []),
            "sql": result.get("sql"),
            "explanation": result.get("explanation", ""),
            "has_chunks": bool(result.get("chunks")),
        }
    except ValueError as e:
        return {"answer_type": "blocked", "rows": 0, "error": str(e)}
    except Exception as e:
        return {"answer_type": "error", "rows": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def check_answer_type(run, example):
    expected = example.outputs.get("expected_type")
    actual = run.outputs.get("answer_type")
    return {"key": "answer_type_correct", "score": int(expected == actual)}


def check_row_count(run, example):
    expected = example.outputs.get("expected_rows", 0)
    actual = run.outputs.get("rows", 0)
    if expected == 0:
        return {"key": "row_count_correct", "score": 1}
    score = 1 if actual == expected else (0.5 if abs(actual - expected) <= 2 else 0)
    return {"key": "row_count_correct", "score": score}


def check_has_explanation(run, example):
    explanation = run.outputs.get("explanation", "")
    score = 1 if explanation and len(explanation) > 10 else 0
    return {"key": "has_explanation", "score": score}


def llm_judge_explanation(run, example):
    """Use Claude to judge if explanation is helpful."""
    explanation = run.outputs.get("explanation", "")
    question = example.inputs.get("question", "")
    answer_type = run.outputs.get("answer_type")

    if answer_type in ("blocked", "rejected") or not explanation:
        return {"key": "explanation_quality", "score": None}

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
        messages=[{
            "role": "user",
            "content": f"""Rate this explanation for the question on a scale 0-1.
Question: {question}
Explanation: {explanation}

Reply with only a number between 0 and 1. 1=very helpful, 0=not helpful or empty."""
        }]
    )
    try:
        score = float(response.content[0].text.strip())
        score = max(0.0, min(1.0, score))
    except Exception:
        score = 0.5
    return {"key": "explanation_quality", "score": score}


def main():
    client = Client(api_key=os.environ["LANGSMITH_API_KEY"])
    create_or_update_dataset(client)

    results = evaluate(
        run_assistant,
        data=DATASET_NAME,
        evaluators=[check_answer_type, check_row_count, check_has_explanation, llm_judge_explanation],
        experiment_prefix="analytics-assistant",
        client=client,
    )

    print("\n=== LANGSMITH RESULTS ===")
    df = results.to_pandas()
    metric_cols = [c for c in df.columns if "score" in c.lower() or c in (
        "feedback.answer_type_correct", "feedback.row_count_correct",
        "feedback.has_explanation", "feedback.explanation_quality"
    )]
    print(df[["inputs.question"] + metric_cols].to_string())
    print(f"\nView full results at: https://smith.langchain.com")


if __name__ == "__main__":
    main()
