import logging
import os
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request, Response
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database

# =========================
# НАСТРОЙКИ
# =========================

TOKEN = "8785410240:AAEzceP8n6AYhgA6Sv5t32Ha8jPgH2MFFa8"  # <-- вставь свой токен
ADMIN_ID = 396415558  # <-- вставь свой Telegram user_id

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", "10000"))

if not RENDER_EXTERNAL_URL:
    raise ValueError("Не найдена переменная окружения RENDER_EXTERNAL_URL")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/telegram"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем приложение Telegram
ptb = Application.builder().token(TOKEN).updater(None).build()


# =========================
# КОМАНДЫ БОТА
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.message:
        await update.message.reply_text(
            f"Привет, {user.first_name}!\n"
            "Я бот для спортивных прогнозов в Шарашкиной конторе.\n"
            "Ставки принимаются скрытно до закрытия приема.\n\n"
            "Команды:\n"
            "/list_matches — показать открытые матчи\n"
            "/add_match Название | hockey/football | 2026-04-01 19:30 — добавить матч (только админ)\n"
            "/set_result <match_id> <голы1> <голы2> — внести итоговый счёт (только админ)"
        )


async def cmd_add_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user.id != ADMIN_ID:
        await update.message.reply_text("Эта команда только для администратора.")
        return

    text = update.message.text.replace("/add_match", "", 1).strip()

    if not text:
        await update.message.reply_text(
            "Формат команды:\n"
            "/add_match Название матча | hockey/football | 2026-04-01 19:30\n\n"
            "Пример:\n"
            "/add_match Динамо Минск – СКА | hockey | 2026-04-01 19:30"
        )
        return

    parts = [p.strip() for p in text.split("|")]

    if len(parts) != 3:
        await update.message.reply_text(
            "Неверный формат.\n"
            "Нужно так:\n"
            "/add_match Название матча | hockey/football | 2026-04-01 19:30"
        )
        return

    name, sport_type, start_time = parts

    if sport_type not in ["football", "hockey"]:
        await update.message.reply_text("Вид спорта должен быть: football или hockey")
        return

    match_id = database.add_match(name, sport_type, start_time)

    await update.message.reply_text(
        f"✅ Матч добавлен.\n"
        f"ID: {match_id}\n"
        f"{name}\n"
        f"{sport_type}\n"
        f"{start_time}"
    )


async def cmd_list_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    matches = database.get_matches_open()

    if not matches:
        await update.message.reply_text("Сейчас нет открытых матчей.")
        return

    text = "Матчи для прогнозов:\n\n"
    keyboard_buttons = []

    for match in matches:
        text += f"{match['id']}. {match['name']} — {match['start_time']}\n"
        keyboard_buttons.append([
            InlineKeyboardButton(
                f"Ставка на матч {match['id']}",
                callback_data=f"bet_match_{match['id']}"
            )
        ])

    if update.effective_user.id == ADMIN_ID:
        keyboard_buttons.append([
            InlineKeyboardButton(
                "🔒 Закрыть приём прогнозов",
                callback_data="admin_close"
            )
        ])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons)
    )


async def start_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    match_id = int(query.data.replace("bet_match_", ""))

    context.user_data["active_match_id"] = match_id
    context.user_data["step"] = "await_goals_home"

    keyboard = [
        [KeyboardButton(str(i)) for i in range(0, 4)],
        [KeyboardButton(str(i)) for i in range(4, 8)],
    ]

    await query.message.reply_text(
        f"Ставка на матч {match_id}\nВведи голы первой команды (0–7)",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )


async def handle_goals_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = update.message.text.strip()

    if not text.isdigit():
        return

    n = int(text)
    if n < 0 or n > 7:
        await update.message.reply_text("Введите цифру от 0 до 7.")
        return

    step = context.user_data.get("step")
    match_id = context.user_data.get("active_match_id")
    user = update.effective_user

    if step == "await_goals_home":
        context.user_data["goals_home"] = n
        context.user_data["step"] = "await_goals_away"

        keyboard = [
            [KeyboardButton(str(i)) for i in range(0, 4)],
            [KeyboardButton(str(i)) for i in range(4, 8)],
        ]

        await update.message.reply_text(
            f"Голы первой команды: {n}\nТеперь введи голы второй команды (0–7)",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return

    if step == "await_goals_away":
        goals_home = context.user_data.get("goals_home")
        goals_away = n

        success = database.save_prediction(
            user.id,
            user.first_name,
            match_id,
            goals_home,
            goals_away
        )

        context.user_data.clear()

        if success:
            await update.message.reply_text(
                f"✅ Прогноз сохранён: {goals_home}:{goals_away}\n"
                "До закрытия приёма он скрыт от всех."
            )
        else:
            await update.message.reply_text(
                "❌ Не удалось сохранить прогноз. Возможно, приём уже закрыт."
            )


async def close_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if user.id != ADMIN_ID:
        await query.answer("Только для администратора", show_alert=True)
        return

    database.close_predictions()
    await query.answer("Приём закрыт")
    await query.message.reply_text("🔒 Приём прогнозов закрыт.")


async def cmd_set_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user.id != ADMIN_ID:
        await update.message.reply_text("Только админ может вводить результат.")
        return

    parts = context.args
    if len(parts) != 3:
        await update.message.reply_text(
            "Формат:\n/set_result <match_id> <голы_1> <голы_2>\nПример: /set_result 1 3 1"
        )
        return

    try:
        match_id = int(parts[0])
        goals_home = int(parts[1])
        goals_away = int(parts[2])
    except ValueError:
        await update.message.reply_text("Нужны числа.")
        return

    match = database.get_match_by_id(match_id)
    if not match:
        await update.message.reply_text("Матч не найден.")
        return

    database.set_final_score(match_id, goals_home, goals_away)
    preds = database.get_predictions_for_match(match_id)

    result_text = (
        f"Матч: {match['name']}\n"
        f"Итоговый счёт: {goals_home}:{goals_away}\n\n"
        "Прогнозы:\n"
    )

    for p in preds:
        score = f"{p['goals_home']}:{p['goals_away']}"
        marker = "✅" if p["is_correct"] else "❌"
        result_text += f"{p['user_name']} — {score} {marker}\n"

    await update.message.reply_text(result_text)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if query.data.startswith("bet_match_"):
        await start_bet(update, context)
    elif query.data == "admin_close":
        await close_predictions(update, context)


# =========================
# FASTAPI + WEBHOOK
# =========================

@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()

    await ptb.initialize()
    await ptb.start()
    await ptb.bot.set_webhook(WEBHOOK_URL)

    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

    yield

    await ptb.bot.delete_webhook()
    await ptb.stop()
    await ptb.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def healthcheck():
    return {"status": "ok", "message": "Bot is running"}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb.bot)
    await ptb.process_update(update)
    return Response(status_code=HTTPStatus.OK)


# =========================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# =========================

ptb.add_handler(CommandHandler("start", start))
ptb.add_handler(CommandHandler("add_match", cmd_add_match))
ptb.add_handler(CommandHandler("list_matches", cmd_list_matches))
ptb.add_handler(CommandHandler("set_result", cmd_set_result))
ptb.add_handler(CallbackQueryHandler(button_handler))
ptb.add_handler(MessageHandler(filters.Regex(r"^[0-7]$"), handle_goals_input))
