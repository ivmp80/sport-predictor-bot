import sqlite3
from datetime import datetime

# Путь к базе данных (будет в корне проекта)
DB_PATH = "predictions.db"


def init_db():
    """Создаёт таблицы, если их нет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sport_type TEXT,
            start_time DATETIME,
            status TEXT DEFAULT 'open',  -- open / closed / finished
            final_score_home INTEGER,
            final_score_away INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            match_id INTEGER,
            goals_home INTEGER,
            goals_away INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_correct BOOLEAN DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def add_match(name, sport_type, start_time):
    """Добавляет матч в базу."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO matches (name, sport_type, start_time) VALUES (?, ?, ?)",
        (name, sport_type, start_time),
    )
    conn.commit()
    last_row = cursor.lastrowid
    conn.close()
    return last_row


def get_matches_open():
    """Возвращает открытые матчи (для ставок)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, sport_type, start_time, status FROM matches "
        "WHERE status = 'open' ORDER BY start_time"
    )
    rows = cursor.fetchall()
    conn.close()

    matches = []
    for row in rows:
        matches.append({
            "id": row[0],
            "name": row[1],
            "sport_type": row[2],
            "start_time": row[3],
            "status": row[4],
        })
    return matches


def get_match_by_id(match_id):
    """Возвращает матч по id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, sport_type, start_time, status, final_score_home, final_score_away "
        "FROM matches WHERE id = ?",
        (match_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "sport_type": row[2],
        "start_time": row[3],
        "status": row[4],
        "final_score_home": row[5],
        "final_score_away": row[6],
    }


def save_prediction(user_id, user_name, match_id, goals_home, goals_away):
    """
    Сохраняет (или обновляет) прогноз пользователя на матч,
    если статус матча 'open'.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверяем, что матч открыт
    cursor.execute("SELECT status FROM matches WHERE id = ?", (match_id,))
    row = cursor.fetchone()
    if not row or row[0] != "open":
        conn.close()
        return False

    # Проверяем, есть ли уже прогноз для этого user_id на match_id
    cursor.execute(
        "SELECT id FROM predictions WHERE user_id = ? AND match_id = ?",
        (user_id, match_id),
    )
    row = cursor.fetchone()

    if row:
        # Обновляем существующий прогноз
        cursor.execute(
            "UPDATE predictions SET goals_home = ?, goals_away = ?, timestamp = ? "
            "WHERE user_id = ? AND match_id = ?",
            (goals_home, goals_away, datetime.now(), user_id, match_id),
        )
    else:
        # Вставляем новый прогноз
        cursor.execute(
            "INSERT INTO predictions (user_id, user_name, match_id, goals_home, goals_away) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, user_name, match_id, goals_home, goals_away),
        )
    conn.commit()
    conn.close()
    return True


def close_predictions():
    """
    Блокирует новые/изменённые прогнозы, ставя всем матчам статус 'closed'.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE matches SET status = 'closed' WHERE status = 'open'")
    conn.commit()
    conn.close()


def set_final_score(match_id, goals_home, goals_away):
    """
    Устанавливает итоговый счет матча и отмечает точные прогнозы.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Устанавливаем итоговый счет
    cursor.execute(
        "UPDATE matches SET final_score_home = ?, final_score_away = ?, status = 'finished' "
        "WHERE id = ?",
        (goals_home, goals_away, match_id),
    )

    # Помечаем точные прогнозы
    cursor.execute(
        "UPDATE predictions "
        "SET is_correct = 1 "
        "WHERE match_id = ? "
        "AND goals_home = ? "
        "AND goals_away = ?",
        (match_id, goals_home, goals_away),
    )

    conn.commit()
    conn.close()


def get_predictions_for_match(match_id):
    """
    Возвращает прогнозы для матча.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id, user_name, goals_home, goals_away, is_correct "
        "FROM predictions WHERE match_id = ? ORDER BY user_name",
        (match_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    predictions = []
    for row in rows:
        predictions.append({
            "user_id": row[0],
            "user_name": row[1],
            "goals_home": row[2],
            "goals_away": row[3],
            "is_correct": bool(row[4]),
        })
    return predictions


def get_matches_closed():
    """Возвращает закрытые матчи (для показа скрытых прогнозов)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, sport_type, start_time, status FROM matches "
        "WHERE status = 'closed' ORDER BY start_time"
    )
    rows = cursor.fetchall()
    conn.close()

    matches = []
    for row in rows:
        matches.append({
            "id": row[0],
            "name": row[1],
            "sport_type": row[2],
            "start_time": row[3],
            "status": row[4],
        })
    return matches
