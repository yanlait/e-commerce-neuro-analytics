"""
Programmatic verification that LangSmith logging is complete and correct.

Best practice: assert observability via the API, not by eyeballing the UI.

Checks:
  1. A graph run produces a trace with the expected node spans.
  2. LLM calls are logged as generations with token counts.
  3. The latest eval experiment has runs with feedback scores + metadata.

Usage: python backend/evals/verify_langsmith.py
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langsmith import Client
from backend.agent.graph import answer

PROJECT = os.environ.get("LANGSMITH_PROJECT", "pet-analytica")
EXPECTED_NODES = {"input_guardrail", "retrieve", "planner", "sql_generate",
                  "sql_validate", "execute", "verify_grounding"}


def check(label: str, ok: bool, detail: str = ""):
    mark = "✓" if ok else "✗"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def verify_graph_tracing(client: Client):
    print("\n1. GRAPH NODE TRACING")
    # produce a fresh traced run
    answer("Top 5 states by number of orders", history=[])
    time.sleep(4)  # allow async trace ingestion

    runs = list(client.list_runs(project_name=PROJECT, limit=50))
    if not check("graph runs found in project", bool(runs), f"{len(runs)} runs"):
        return

    names = {r.name for r in runs}
    seen_nodes = EXPECTED_NODES & names
    check("node spans present", len(seen_nodes) >= 4,
          f"{sorted(seen_nodes)}")

    # LLM generation runs with token usage
    llm_runs = [r for r in runs if r.run_type == "llm"]
    check("LLM calls traced as generations", bool(llm_runs), f"{len(llm_runs)} llm runs")
    if llm_runs:
        with_tokens = [r for r in llm_runs if (r.total_tokens or 0) > 0]
        check("generations carry token counts", bool(with_tokens),
              f"{len(with_tokens)}/{len(llm_runs)} have tokens")


def verify_experiment(client: Client):
    print("\n2. EVAL EXPERIMENT COMPLETENESS")
    # find the most recent experiment on our dataset
    try:
        projects = sorted(
            [p for p in client.list_projects() if p.reference_dataset_id],
            key=lambda p: p.start_time or 0, reverse=True,
        )
    except Exception as e:
        check("list experiments", False, str(e))
        return
    if not check("experiments exist", bool(projects)):
        return

    exp = projects[0]
    print(f"      latest experiment: {exp.name}")
    exp_runs = list(client.list_runs(project_name=exp.name, is_root=True))
    check("experiment has example runs", bool(exp_runs), f"{len(exp_runs)} runs")

    # metadata present in outputs
    with_model = [r for r in exp_runs if (r.outputs or {}).get("model")]
    check("runs carry model metadata", bool(with_model),
          f"{len(with_model)}/{len(exp_runs)}")
    with_cost = [r for r in exp_runs if (r.outputs or {}).get("cost_usd") is not None]
    check("runs carry cost metadata", bool(with_cost),
          f"{len(with_cost)}/{len(exp_runs)}")

    # feedback scores attached
    total_fb = 0
    for r in exp_runs[:5]:
        fb = list(client.list_feedback(run_ids=[r.id]))
        total_fb += len(fb)
    check("feedback scores attached to runs", total_fb > 0,
          f"{total_fb} scores on first 5 runs")


def main():
    client = Client(api_key=os.environ["LANGSMITH_API_KEY"])
    print(f"Verifying LangSmith logging (project='{PROJECT}')")
    verify_graph_tracing(client)
    verify_experiment(client)
    print("\nDone. Inspect traces at https://smith.langchain.com")


if __name__ == "__main__":
    main()
