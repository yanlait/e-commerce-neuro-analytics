"""
LangSmith evaluation runner.

Usage:
    # Full eval with LLM judge (costs ~$0.10)
    python backend/evals/run_langsmith.py

    # Fast eval — no LLM calls
    python backend/evals/run_langsmith.py --fast

    # Single category
    python backend/evals/run_langsmith.py --category security
"""
import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langsmith import Client
from langsmith.evaluation import evaluate as ls_evaluate
from backend.agent.planner import answer
from backend.evals.evaluators import ALL, FAST

DATASET_NAME = "olist-analytics-golden"
GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"


def load_examples(category: str | None = None) -> list[dict]:
    examples = json.loads(GOLDEN_PATH.read_text())
    if category:
        examples = [e for e in examples if e["category"] == category]
    return examples


def create_dataset(client: Client, examples: list[dict]):
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        client.delete_dataset(dataset_id=existing[0].id)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Golden dataset for Olist analytics assistant — 30 cases across 6 categories",
    )
    client.create_examples(
        inputs=[{"question": e["question"], "followup": e.get("followup")} for e in examples],
        outputs=[{k: v for k, v in e.items() if k not in ("question", "followup")} for e in examples],
        dataset_id=dataset.id,
    )
    print(f"Dataset '{DATASET_NAME}': {len(examples)} examples")
    return dataset


def run_assistant(inputs: dict) -> dict:
    question = inputs["question"]
    history = []

    # handle followup questions
    if inputs.get("followup"):
        first = answer(question, history=[])
        sql = first.get("sql") or ""
        history = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": sql or first.get("explanation", "")},
        ]
        question = inputs["followup"]

    try:
        result = answer(question, history=history)
        answer_type = result.get("answer_type")
        if not answer_type:
            answer_type = "rag" if not result.get("sql") else "sql"
        return {
            "answer_type": answer_type,
            "rows": len(result.get("data") or []),
            "sql": result.get("sql"),
            "explanation": result.get("explanation", ""),
            "data": result.get("data") or [],
            "has_chunks": bool(result.get("chunks")),
            "model": result.get("model"),
            "provider": result.get("provider"),
            "cost_usd": result.get("cost_usd"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "llm_latency_ms": result.get("latency_ms"),
        }
    except ValueError as e:
        return {"answer_type": "blocked", "rows": 0, "sql": None, "explanation": str(e), "data": []}
    except Exception as e:
        return {"answer_type": "error", "rows": 0, "sql": None, "explanation": str(e), "data": []}


def print_summary(results):
    df = results.to_pandas()
    score_cols = [c for c in df.columns if c.startswith("feedback.")]

    print("\n" + "="*60)
    print("EVALUATION SUMMARY")
    print("="*60)

    # cost/latency are measurements, not pass/fail metrics
    MEASUREMENTS = {"cost_usd", "llm_latency_ms"}

    for col in score_cols:
        metric = col.replace("feedback.", "")
        vals = df[col].dropna()
        if len(vals) == 0:
            continue
        avg = vals.mean()
        if metric in MEASUREMENTS:
            total = vals.sum()
            unit = "$" if "cost" in metric else "ms"
            print(f"  {metric:<30} avg={avg:.4f}{unit}  total={total:.4f}{unit}")
        else:
            passed = (vals >= 0.8).sum()
            print(f"  {metric:<30} avg={avg:.2f}  passed={passed}/{len(vals)}")

    print()
    # show failures
    if "feedback.answer_type_correct" in df.columns:
        failures = df[df["feedback.answer_type_correct"] < 1][["inputs.question", "feedback.answer_type_correct"]]
        if not failures.empty:
            print("ANSWER TYPE FAILURES:")
            for _, row in failures.iterrows():
                print(f"  ✗ {row['inputs.question']}")

    print(f"\nView at: https://smith.langchain.com")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Skip LLM judge evaluators")
    parser.add_argument("--category", help="Run only this category")
    args = parser.parse_args()

    client = Client(api_key=os.environ["LANGSMITH_API_KEY"])
    examples = load_examples(args.category)
    create_dataset(client, examples)

    evaluators = FAST if args.fast else ALL
    mode = "fast" if args.fast else "full"
    cat = args.category or "all"

    print(f"\nRunning {mode} eval on {cat} categories ({len(examples)} cases)...")

    results = ls_evaluate(
        run_assistant,
        data=DATASET_NAME,
        evaluators=evaluators,
        experiment_prefix=f"analytics-{cat}-{mode}",
        client=client,
    )

    print_summary(results)


if __name__ == "__main__":
    main()
