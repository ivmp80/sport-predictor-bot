import logging
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Вставь свой токен прямо сюда
TOKEN = "8785410240:AAEzceP8n6AYhgA6Sv5t32Ha8jPgH2MFFa8"  # ← ЗАМЕНИ НА СВОЙ ТОКЕН

# Подключаем базу
import database

# ----------------- Настройка логирования -----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ----------------- Команда /start -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Сейчас я буду ботом для спортивных прогнозов.\n"
        "Точные счета вводятся через кнопки.\n"
        "Пока прогнозы скрыты, пока админ не нажнёт, что приём закрыт."
    )


# ----------------- Команда /add_match (для админа) -----------------

ADMIN_ID = 396415558  # ← ЗАМЕНИ НА СВОЙ user_id из Telegram (можно узнать через @userinfobot)

async def cmd_add_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user.id != ADMIN_ID:
        await update.message.reply_text("Эта команда только для администратора.")
        return

    context.user_data["step"] = "await_match_name"
    await update.message.reply_text(
        "Введи название матча, например:\n«Россия – Чехия, хоккей»"
    )


async def handle_match_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text.strip()

    step = context.user_data.get("step")

    if step == "await_match_name":
        context.user_data["match_name"] = text
        context.user_data["step"] = "await_sport_type"
        await update.message.reply_text(
            "Выбери вид спорта:\n1 – футбол\n2 – хоккей"
        )
    elif step == "await_sport_type":
        sport_map = {"1": "football", "2": "hockey"}
        sport_type = sport_map.get(text)
        if not sport_type:
            await update.message.reply_text("Выбери 1 или 2.")
            return

        context.user_data["sport_type"] = sport_type
        context.user_data["step"] = "await_start_time"

        await update.message.reply_text(
            "Введи дату и время в формате ГГГГ-ММ-ДД ЧЧ:ММ, например:\n2026-03-31 20:00"
        )
    elif step == "await_start_time":
        start_time_str = text
        # Можно добавить валидацию, но пока упростим
        try:
            dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "Неверный формат. Используй пример:\n2026-03-31 20:00"
            )
            return

        name = context.user_data["match_name"]
        sport_type = context.user_data["sport_type"]
        id = database.add_match(name, sport_type, start_time_str)
        # Очистим шаг
        context.user_data.pop("step", None)

        await update.message.reply_text(
            f"✅ Матч добавлен (ID={id}):\n{name}\nВремя: {start_time_str}"
        )


# ----------------- Публикация матчей в чате -----------------

async def cmd_list_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    matches = database.get_matches_open()
    if not matches:
        await update.message.reply_text("Сейчас нет открытых матчей.")
        return

    text = "Спортивный день:\n\n"
    keyboard_buttons = []

    for match in matches:
        line = f"{match['id']}. {match['name']} — {match['start_time']}"
        text += line + "\n"

        btn = InlineKeyboardButton(
            f"Ставка на матч {match['id']}",
            callback_data=f"bet_match_{match['id']}"
        )
        keyboard_buttons.append([btn])

    # Кнопка закрыть приём (только для админа)
    if update.effective_user.id == ADMIN_ID:
        keyboard_buttons.append(
            [InlineKeyboardButton("🔒 Закрыть приём прогнозов", callback_data="admin_close")]
        )

    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_text(text, reply_markup=keyboard)


# ----------------- Ввод счёта через кнопки -----------------

async def start_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    # format: "bet_match_123"
    _, match_id_s = query.data.split("_", 2)
    match_id = int(match_id_s)

    context.user_data["active_match_id"] = match_id
    context.user_data["step"] = "await_goals_home"

    # Кнопки 0–7
    keyboard = [
        [KeyboardButton(str(i)) for i in range(0, 4)],
        [KeyboardButton(str(i)) for i in range(4, 8)],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await query.message.reply_text(
        f"Ставка на матч {match_id}:\n" 
        "Введите голы первой команды (0–7)",
        reply_markup=reply_markup
    )


async def handle_goals_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    try:
        n = int(text)
        if n < 0 or n > 7:
            raise ValueError
    except ValueError:
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
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"Голы первой команды: {n}\n"
            "Теперь введи голы второй команды (0–7)",
            reply_markup=reply_markup
        )
    elif step == "await_goals_away":
        context.user_data["goals_away"] = n
        context.user_data.pop("step", None)
        context.user_data.pop("active_match_id", None)

        goals_home = context.user_data["goals_home"]
        goals_away = context.user_data["goals_away"]

        # Сохраняем прогноз
        success = database.save_prediction(
            user.id,
            user.first_name,
            match_id,
            goals_home,
            goals_away
        )
        if success:
            await update.message.reply_text(
                f"⚽ Прогноз принят!\n"
                f"Счет: {goals_home}:{goals_away}\n"
                f"Матч ID: {match_id}\n"
                "Пока он не виден остальным игрокам."
            )
        # Если неудачно (например, статус уже closed)
        # в database.save_prediction будет return False
        else:
            await update.message.reply_text(
                "❌ Ошибка: сейчас приём прогнозов для этого матча закрыт."
            )


# ----------------- Закрытие приёма прогнозов -----------------

async def close_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if user.id != ADMIN_ID:
        await query.answer("Эта кнопка только для администратора.", show_alert=True)
        return

    await query.answer("Приём прогнозов закрыт.")
    database.close_predictions()
    await query.message.reply_text("🔒 Приём прогнозов на все матчи закрыт.")


# ----------------- Команда /set_result (для админа) -----------------

async def cmd_set_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user.id != ADMIN_ID:
        await update.message.reply_text("Только админ может вводить итоговый счёт.")
        return

    # Формат: /set_result <match_id> <home> <away>
    # Например: /set_result 1 3 1
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

    # Записываем итоговый счёт и помечаем точные прогнозы
    database.set_final_score(match_id, goals_home, goals_away)

    # Получаем прогнозы
    preds = database.get_predictions_for_match(match_id)

    result_text = (
        f"Матч: {match['name']}\n"
        f"Итоговый счёт: {goals_home}:{goals_away}\n\n"
        f"Прогнозы:\n"
    )

    for p in preds:
        score = f"{p['goals_home']}:{p['goals_away']}"
        marker = "✅" if p["is_correct"] else "❌"
        result_text += f"@{p['user_name']} – {score} {marker}\n"

    await update.message.reply_text(result_text)


# ----------------- Обработчики callback-запросов -----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if query.data.startswith("bet_match_"):
        await start_bet(update, context)
    elif query.data == "admin_close":
        await close_predictions(update, context)


# ----------------- Запуск бота -----------------

def main():
    # Инициализируем базу
    database.init_db()

    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add_match", cmd_add_match))
    application.add_handler(CommandHandler("list_matches", cmd_list_matches))
    application.add_handler(CommandHandler("set_result", cmd_set_result))

    # Обработчик для ввода матчей (текст после /add_match)
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r".*"), handle_match_input)
    )

    # Обработчик цифр для ввода счёта
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(r"^[0-7]$"), handle_goals_input)
    )

    # Обработчик inline-кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запуск
    logger.info("Запускаем бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
