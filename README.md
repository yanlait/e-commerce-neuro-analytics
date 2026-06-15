# AI Analytics Assistant

Chat with e-commerce data in natural language. Ask questions, get SQL + results.

Built on the [Olist Brazil dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — 100k orders, 8 tables.

## Architecture

```
Telegram Bot
     │
     ▼
FastAPI  ──►  Ollama (LLM)  ──►  DuckDB (SQL execution)
     │              │
     │         Langfuse (prompt store + tracing)
     │
     ▼
ChromaDB (RAG over docs)     SQLite (query log)
```

## Stack

| Layer | Technology |
|---|---|
| LLM | Ollama (local) / OpenAI API |
| SQL engine | DuckDB |
| Vector search | ChromaDB + sentence-transformers |
| Semantic layer | YAML schema with metrics definitions |
| Observability | Langfuse (prompt versioning, trace logging) |
| API | FastAPI |
| Bot | python-telegram-bot |
| Evals | pytest |

## Features

- **Natural language → SQL** — LLM generates DuckDB queries from user questions
- **Semantic layer** — YAML schema prevents column hallucinations
- **RAG** — retrieves relevant metric definitions and glossary before answering
- **Prompt management** — prompts versioned in Langfuse, editable without code deploys
- **Observability** — every request traced: prompt, SQL, retrieved chunks, latency
- **SQL injection protection** — blocks DDL statements and unbounded SELECT *
- **Eval suite** — 13 tests covering SQL quality, safety, and RAG retrieval

## Quickstart

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Download Olist dataset from Kaggle → data/raw/
# https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

# 3. Convert CSVs to parquet
python scripts/load_data.py

# 4. Start Langfuse (observability UI at http://localhost:3001)
docker compose -f docker/docker-compose.yml up -d

# 5. Index docs for RAG
python -c "from backend.rag.retriever import index_docs; index_docs()"

# 6. Run API
uvicorn backend.api.main:app --reload

# 7. Run Telegram bot
python bot/main.py

# 8. Run evals
pytest backend/evals/ -v
```

## Environment variables

```bash
# .env
ANTHROPIC_API_KEY=...        # optional, if switching from Ollama to Claude
LANGFUSE_SECRET_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_HOST=http://localhost:3001
TELEGRAM_BOT_TOKEN=...
```

## Example questions

```
Top 5 product categories by revenue
Average review score by state
Monthly revenue in 2017
Top 10 customers by LTV
Which payment method is most popular?
What is freight_value?
```

## Eval results

```
13 passed in ~60s
  - SQL quality:  7/7
  - Safety:       4/4  (SQL injection, prompt injection, unbounded SELECT *)
  - RAG:          2/2
```
