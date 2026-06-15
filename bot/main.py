import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

load_dotenv()

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from backend.agent.planner import answer


def format_response(question: str, result: dict) -> str:
    parts = []

    if result.get("data"):
        rows = result["data"]
        # table header
        if rows:
            keys = list(rows[0].keys())
            header = " | ".join(keys)
            sep = " | ".join(["---"] * len(keys))
            rows_str = "\n".join(
                " | ".join(str(round(row[k], 2) if isinstance(row[k], float) else row[k]) for k in keys)
                for row in rows[:10]
            )
            parts.append(f"```\n{header}\n{sep}\n{rows_str}\n```")
            if len(result["data"]) > 10:
                parts.append(f"_...и ещё {len(result['data']) - 10} строк_")

    if result.get("sql"):
        parts.append(f"```sql\n{result['sql']}\n```")

    if not parts:
        parts.append("Не удалось получить данные по этому вопросу.")

    return "\n\n".join(parts)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я аналитический ассистент по e-commerce данным Olist.\n\n"
        "Задай вопрос на английском, например:\n"
        "• Top 5 product categories by revenue\n"
        "• Average review score by state\n"
        "• Monthly revenue in 2018"
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    await update.message.reply_text("Думаю...")

    try:
        result = answer(question, history=[])
        text = format_response(question, result)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
