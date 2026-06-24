import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from langfuse import Langfuse

load_dotenv()

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from backend.agent.planner import answer
from backend.agent.tracer import _lf

# trace_id хранится между хендлерами через user_data
# key: message_id → trace_id


def format_response(result: dict) -> str:
    parts = []

    if result.get("data"):
        rows = result["data"]
        if rows:
            keys = list(rows[0].keys())
            header = " | ".join(keys)
            sep = " | ".join(["---"] * len(keys))
            rows_str = "\n".join(
                " | ".join(str(round(row[k], 2) if isinstance(row[k], float) else row[k]) for k in keys)
                for row in rows[:10]
            )
            parts.append(f"{header}\n{sep}\n{rows_str}")
            if len(result["data"]) > 10:
                parts.append(f"...и ещё {len(result['data']) - 10} строк")

    if result.get("sql"):
        parts.append(f"SQL:\n{result['sql']}")

    # show RAG context if no data or empty result
    data = result.get("data")
    no_data = not data or all(
        v is None or (isinstance(v, float) and v != v)
        for row in data for v in row.values()
    )
    if (not parts or no_data) and result.get("chunks"):
        parts.append("Dataset context:")
        for chunk in result["chunks"][:1]:
            parts.append(f"[{chunk['source']}]\n{chunk['text'][:400]}")

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

        if result.get("message"):
            await update.message.reply_text(result["message"])
            return

        text = format_response(result)
        trace_id = result.get("trace_id")

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍", callback_data=f"feedback:1:{trace_id}"),
                InlineKeyboardButton("👎", callback_data=f"feedback:0:{trace_id}"),
            ]
        ])
        msg = await update.message.reply_text(text, reply_markup=keyboard)

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def handle_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, score_str, trace_id = query.data.split(":", 2)
    score = int(score_str)

    if trace_id and trace_id != "None":
        _lf.score(
            trace_id=trace_id,
            name="user-feedback",
            value=score,
            comment="👍" if score == 1 else "👎",
        )

    emoji = "👍" if score == 1 else "👎"
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"Спасибо за оценку {emoji}")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern="^feedback:"))
    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
