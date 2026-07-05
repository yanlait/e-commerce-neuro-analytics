# AI Analytics Assistant

Natural-language analytics assistant over the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (~100k orders, 8 tables). Ask a question in plain language — a **LangGraph multi-agent** pipeline decides whether to answer with SQL over the data or with retrieved documentation, self-corrects broken SQL, and enforces safety guardrails.

Built as an evaluation-first project: the agent ships with a golden dataset, tiered
evaluators (deterministic → heuristic → LLM-as-judge), online + offline tracing, and a
CI/CD quality gate that blocks regressions.

## Agent graph

```
                          ┌──────────────────┐
   user question ───────► │  input_guardrail │  intent / injection safety
                          └──────────────────┘
                             │            │ unsafe
                             │ ok         ▼
                             ▼         ┌────────┐
                        ┌──────────┐   │ reject │──► END
                        │ retrieve │   └────────┘
                        └──────────┘   metric defs + context (feed generation)
                             ▼
                        ┌──────────┐
                        │ planner  │   tool selection: sql vs rag
                        └──────────┘
                          │        │ rag
                    sql   │        ▼
                          ▼    ┌────────────┐
                  ┌─────────────┐ │ rag_answer │──► END
                  │ sql_generate│ └────────────┘
                  └─────────────┘   (schema + retrieved defs)
                        ▼
                  ┌─────────────┐   guardrails + EXPLAIN dry-run
                  │ sql_validate│◄─────────────┐
                  └─────────────┘              │ repair (feed error back)
                    │     │  invalid & tries<N │
              valid │     └────────────────────┘
                    ▼            │ exhausted → graceful_fail → END
                  ┌─────────┐
                  │ execute │   run SQL; empty → rag_enrich → END
                  └─────────┘
                        ▼
                  ┌──────────────────┐
                  │ verify_grounding │   cheap faithfulness check
                  └──────────────────┘
                        ▼
                       END
```

Each node maps to a distinct quality dimension, so it can be evaluated in isolation
(routing accuracy, retrieval precision, SQL validity, grounding).

## Stack

| Layer | Technology |
|---|---|
| Orchestration | **LangGraph** (multi-agent state graph) |
| LLM | swappable: OpenAI `gpt-4o-mini` / Anthropic / local Ollama (`LLM_PROVIDER`) |
| SQL engine | DuckDB over Parquet |
| Vector search | ChromaDB + sentence-transformers |
| Semantic layer | YAML schema with metric definitions |
| Prompt store | Langfuse (versioned, with local file fallback) |
| Online tracing | Langfuse (per-request) + LangSmith (node-level spans) |
| Offline evals | LangSmith experiments + golden dataset |
| CI gate | GitHub Actions + threshold checks |
| Bot | python-telegram-bot |

## Key features

- **Multi-agent graph** — explicit router → retrieve → plan → generate → validate → execute → verify flow
- **Retrieval-before-generation** — metric definitions are retrieved and injected into SQL generation (kills the "revenue from wrong table" class of errors)
- **Self-correcting SQL** — `EXPLAIN` dry-run validates queries; DB errors are fed back to the model for up to N repair attempts
- **Layered guardrails** — DDL blocking, `SELECT *`/unbounded-query limits, PII protection (no row-level access to identity tables), and a hard result-row cap
- **Cost & latency tracking** — every LLM call records tokens, cost, and latency into Langfuse, LangSmith, and SQLite
- **Model comparison** — one env var swaps the model under test; run the same golden dataset across providers

## Evaluation system

The heart of the project. Three tiers of evaluators run over a 30-case golden dataset
(`backend/evals/golden_dataset.json`) spanning 6 categories: `sql_correct`, `rag_correct`,
`edge_case`, `security`, `rejected`, `followup`.

| Tier | Examples | Cost |
|---|---|---|
| Deterministic | answer_type, row_count, sql_valid, security_safe, cost, latency | free |
| Heuristic | numeric_value vs ground truth, keyword presence, has_explanation | free |
| LLM-as-judge | explanation_quality, faithfulness (Claude Haiku) | ~cents |

The judge runs on a **different provider** (Anthropic) than the system under test (OpenAI)
to reduce self-preference bias.

```bash
# offline experiment (logs to LangSmith, compares graph vs planner)
AGENT_IMPL=graph python backend/evals/run_langsmith.py            # full, with judge
AGENT_IMPL=graph python backend/evals/run_langsmith.py --fast     # no LLM judge

# local quality gate (full numeric ground truth)
python backend/evals/gate.py
```

### Graph vs linear-planner (A/B on golden dataset)

| Metric | linear planner | LangGraph | 
|---|---|---|
| answer_type_correct | 0.73 | **0.97** |
| numeric_value_correct | 0.17 | **1.00** |
| security_safe | 0.80 | **1.00** |
| cost / latency | lower | +45% / +20% |

The graph trades cost/latency for large quality gains — a measurable, documented tradeoff.

## CI/CD eval gate

`.github/workflows/eval-gate.yml` runs on every PR that touches the agent, prompts, or
docs. Two-tier design:

- **CI** — runs the golden dataset through the graph on a 1.4MB referentially-consistent
  fixture (`backend/evals/fixtures/`), checking behaviour/safety/routing against
  `thresholds.ci.json`. Fast, cheap, needs no full dataset.
- **Local / nightly** — full numeric ground-truth checks against the real 38MB dataset
  (`thresholds.json`).

The gate exits non-zero on any threshold breach → **blocks the merge** and posts a metric
table as a PR comment.

## Quickstart

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Download Olist dataset from Kaggle → data/raw/
#    https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
python scripts/load_data.py            # CSV → Parquet

# 3. Index docs for RAG
python -c "from backend.rag.retriever import index_docs; index_docs()"

# 4. (optional) Start Langfuse — prompt store + tracing UI at http://localhost:3001
docker compose -f docker/docker-compose.yml up -d

# 5. Run the Telegram bot (or import backend.agent.graph.answer directly)
python bot/main.py

# 6. Run evals / gate
python backend/evals/gate.py
```

## Environment variables

```bash
# LLM provider (system under test)
LLM_PROVIDER=openai          # openai | anthropic | ollama
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...         # used by LLM-as-judge evaluators

# Observability
LANGFUSE_SECRET_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_HOST=http://localhost:3001
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true        # node-level graph tracing
LANGSMITH_PROJECT=pet-analytica

TELEGRAM_BOT_TOKEN=...
```

## Repository layout

```
backend/
  agent/
    graph.py          LangGraph multi-agent orchestration
    classifier.py     intent / safety gate
    router.py         sql-vs-rag tool selection
    sql_generator.py  NL → SQL (JSON), context-aware + repair
    sql_runner.py     guardrails, EXPLAIN validation, execution
    llm.py            swappable provider + cost/latency/token metering
    tracer.py         Langfuse tracing
    query_log.py      SQLite request log
    planner.py        legacy linear router (kept for A/B)
    prompts/          local fallback prompts
  rag/retriever.py    ChromaDB retrieval over docs/
  semantic_layer/     metrics.yaml (schema + metric SQL)
  evals/
    golden_dataset.json   30 cases, 6 categories
    evaluators.py         deterministic / heuristic / LLM-judge
    run_langsmith.py      offline experiments
    gate.py               CI/CD quality gate
    thresholds*.json      pass/fail thresholds (full + ci)
    fixtures/             1.4MB CI dataset
docs/                 markdown knowledge base for RAG
bot/                  Telegram interface
.github/workflows/    eval-gate.yml
```
