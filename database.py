import sqlite3

DB_PATH = "predictions.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sport_type TEXT NOT NULL,
        start_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        final_home INTEGER,
        final_away INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        match_id INTEGER NOT NULL,
        goals_home INTEGER NOT NULL,
        goals_away INTEGER NOT NULL,
        is_correct INTEGER DEFAULT 0,
        UNIQUE(user_id, match_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        user_name TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_user(user_id, user_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, user_name)
        VALUES (?, ?)
    """, (user_id, user_name))

    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, user_name FROM users")
    rows = cursor.fetchall()
    conn.close()

    users = []
    for row in rows:
        users.append({
            "user_id": row[0],
            "user_name": row[1],
        })
    return users


def add_match(name, sport_type, start_time):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO matches (name, sport_type, start_time, status)
        VALUES (?, ?, ?, 'open')
    """, (name, sport_type, start_time))

    match_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return match_id


def get_matches_open():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, sport_type, start_time, status
        FROM matches
        WHERE status = 'open'
        ORDER BY start_time
    """)
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


def get_matches_closed():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, sport_type, start_time, status
        FROM matches
        WHERE status = 'closed'
        ORDER BY start_time
    """)
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, sport_type, start_time, status, final_home, final_away
        FROM matches
        WHERE id = ?
    """, (match_id,))
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
        "final_home": row[5],
        "final_away": row[6],
    }


def save_prediction(user_id, user_name, match_id, goals_home, goals_away):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM matches WHERE id = ?", (match_id,))
    row = cursor.fetchone()

    if not row or row[0] != "open":
        conn.close()
        return False

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO predictions
            (user_id, user_name, match_id, goals_home, goals_away)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, user_name, match_id, goals_home, goals_away))
        conn.commit()
        success = True
    except Exception:
        success = False

    conn.close()
    return success


def get_predictions_for_match(match_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, user_name, goals_home, goals_away, is_correct
        FROM predictions
        WHERE match_id = ?
        ORDER BY user_name
    """, (match_id,))
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


def get_players_for_match(match_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT user_name
        FROM predictions
        WHERE match_id = ?
        ORDER BY user_name
    """, (match_id,))
    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]


def close_predictions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE matches
        SET status = 'closed'
        WHERE status = 'open'
    """)

    conn.commit()
    conn.close()


def set_final_score(match_id, goals_home, goals_away):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE matches
        SET final_home = ?, final_away = ?, status = 'finished'
        WHERE id = ?
    """, (goals_home, goals_away, match_id))

    cursor.execute("""
        UPDATE predictions
        SET is_correct = CASE
            WHEN goals_home = ? AND goals_away = ? THEN 1
            ELSE 0
        END
        WHERE match_id = ?
    """, (goals_home, goals_away, match_id))

    conn.commit()
    conn.close()
