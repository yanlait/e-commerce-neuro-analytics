"""
CI/CD evaluation gate.

Runs the golden dataset through the agent, applies the FAST evaluators
(deterministic + heuristic — no LLM judge, so cheap and reproducible in CI),
aggregates per-metric scores, and compares them to thresholds.json.

Exit code 0 = all gates pass, 1 = a regression breached a threshold.

Usage:
    python backend/evals/gate.py
    python backend/evals/gate.py --markdown gate_report.md   # for PR comment
"""
import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.evals.evaluators import FAST

AGENT_IMPL = os.environ.get("AGENT_IMPL", "graph")
if AGENT_IMPL == "graph":
    from backend.agent.graph import answer
else:
    from backend.agent.planner import answer

HERE = Path(__file__).parent
GOLDEN = json.loads((HERE / "golden_dataset.json").read_text())

# GATE_PROFILE=ci → lightweight thresholds on the fixture (structural/safety only)
# GATE_PROFILE=full (default) → full thresholds including numeric ground truth
GATE_PROFILE = os.environ.get("GATE_PROFILE", "full")
_THRESH_FILE = "thresholds.ci.json" if GATE_PROFILE == "ci" else "thresholds.json"
THRESHOLDS = json.loads((HERE / _THRESH_FILE).read_text())


# lightweight shims so evaluators (written for LangSmith) work offline
class _Run:
    def __init__(self, outputs):
        self.outputs = outputs


class _Example:
    def __init__(self, inputs, outputs):
        self.inputs = inputs
        self.outputs = outputs


def run_case(case: dict) -> dict:
    question = case["question"]
    history = []
    if case.get("followup"):
        first = answer(question, history=[])
        history = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": first.get("sql") or first.get("explanation", "")},
        ]
        question = case["followup"]
    try:
        r = answer(question, history=history)
        atype = r.get("answer_type") or ("sql" if r.get("sql") else "rag")
        return {
            "answer_type": atype,
            "rows": len(r.get("data") or []),
            "sql": r.get("sql"),
            "explanation": r.get("explanation", ""),
            "data": r.get("data") or [],
            "chunks_text": " ".join(c.get("text", "") for c in (r.get("chunks") or [])),
            "model": r.get("model"),
            "cost_usd": r.get("cost_usd"),
            "llm_latency_ms": r.get("latency_ms"),
        }
    except Exception as e:
        return {"answer_type": "error", "rows": 0, "sql": None,
                "explanation": str(e), "data": [], "chunks_text": ""}


def evaluate_all() -> dict:
    scores = defaultdict(list)
    for case in GOLDEN:
        outputs = run_case(case)
        run = _Run(outputs)
        example = _Example({"question": case["question"], "followup": case.get("followup")}, case)
        for evaluator in FAST:
            res = evaluator(run, example)
            if res and res.get("score") is not None:
                scores[res["key"]].append(res["score"])
    return {k: sum(v) / len(v) for k, v in scores.items() if v}


def check_gates(metrics: dict) -> list[dict]:
    results = []
    for metric, threshold in THRESHOLDS.get("min", {}).items():
        actual = metrics.get(metric)
        if actual is None:
            results.append({"metric": metric, "kind": "min", "threshold": threshold,
                            "actual": None, "passed": None})
            continue
        results.append({"metric": metric, "kind": "min", "threshold": threshold,
                        "actual": actual, "passed": actual >= threshold})
    for metric, threshold in THRESHOLDS.get("max", {}).items():
        actual = metrics.get(metric)
        if actual is None:
            results.append({"metric": metric, "kind": "max", "threshold": threshold,
                            "actual": None, "passed": None})
            continue
        results.append({"metric": metric, "kind": "max", "threshold": threshold,
                        "actual": actual, "passed": actual <= threshold})
    return results


def render(results: list[dict], markdown: bool) -> str:
    lines = []
    if markdown:
        lines.append(f"### Eval Gate — `{AGENT_IMPL}` on {len(GOLDEN)} golden cases\n")
        lines.append("| Metric | Threshold | Actual | Status |")
        lines.append("|---|---|---|---|")
        for r in results:
            actual = "—" if r["actual"] is None else (
                f"{r['actual']:.0f}" if r["actual"] > 10 else f"{r['actual']:.2f}")
            op = "≥" if r["kind"] == "min" else "≤"
            status = "⚪ n/a" if r["passed"] is None else ("✅" if r["passed"] else "❌")
            lines.append(f"| {r['metric']} | {op} {r['threshold']} | {actual} | {status} |")
    else:
        lines.append(f"\nEVAL GATE ({AGENT_IMPL}, {len(GOLDEN)} cases)")
        lines.append("=" * 55)
        for r in results:
            actual = "n/a" if r["actual"] is None else (
                f"{r['actual']:.0f}" if r["actual"] > 10 else f"{r['actual']:.2f}")
            op = ">=" if r["kind"] == "min" else "<="
            status = "SKIP" if r["passed"] is None else ("PASS" if r["passed"] else "FAIL")
            lines.append(f"  [{status}] {r['metric']:<28} {op} {r['threshold']}  (got {actual})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", help="write a markdown report to this path")
    args = parser.parse_args()

    print(f"Running eval gate on {len(GOLDEN)} cases ({AGENT_IMPL})...")
    metrics = evaluate_all()
    results = check_gates(metrics)

    print(render(results, markdown=False))
    if args.markdown:
        Path(args.markdown).write_text(render(results, markdown=True))

    failed = [r for r in results if r["passed"] is False]
    if failed:
        print(f"\n❌ GATE FAILED: {len(failed)} metric(s) below threshold")
        for r in failed:
            print(f"   - {r['metric']}: {r['actual']:.2f} vs {r['threshold']}")
        sys.exit(1)
    print("\n✅ GATE PASSED — all metrics within thresholds")
    sys.exit(0)


if __name__ == "__main__":
    main()
