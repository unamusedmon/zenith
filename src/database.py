"""SQLite persistence layer."""
import sqlite3
import os
from datetime import datetime, timedelta


DB_PATH = os.path.join(os.path.expanduser("~"), ".local", "share", "zenith")
os.makedirs(DB_PATH, exist_ok=True)
DB_FILE = os.path.join(DB_PATH, "zenith.db")


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            completed INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS energy_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value INTEGER NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS worries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            dismissed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def add_session(session_type, duration, completed=True):
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (type, duration_seconds, completed) VALUES (?, ?, ?)",
        (session_type, duration, completed),
    )
    conn.commit()
    conn.close()


def add_capture(text):
    conn = get_connection()
    conn.execute("INSERT INTO captures (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()


def get_captures(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM captures ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_capture(capture_id):
    conn = get_connection()
    conn.execute("DELETE FROM captures WHERE id = ?", (capture_id,))
    conn.commit()
    conn.close()


def add_energy(value, note=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO energy_entries (value, note) VALUES (?, ?)", (value, note)
    )
    conn.commit()
    conn.close()


def get_energy_entries(limit=30):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM energy_entries ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_energy():
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT * FROM energy_entries WHERE created_at LIKE ? ORDER BY created_at DESC LIMIT 1",
        (f"{today}%",),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_worry(text):
    conn = get_connection()
    conn.execute("INSERT INTO worries (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()


def dismiss_worry(worry_id):
    conn = get_connection()
    conn.execute("UPDATE worries SET dismissed = 1 WHERE id = ?", (worry_id,))
    conn.commit()
    conn.close()


def get_active_worries():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM worries WHERE dismissed = 0 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = get_connection()
    total_sessions = conn.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE completed = 1"
    ).fetchone()["count"]

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_sessions = conn.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE completed = 1 AND created_at >= ?",
        (week_ago,),
    ).fetchone()["count"]

    total_minutes = conn.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0) / 60 as mins FROM sessions WHERE completed = 1"
    ).fetchone()["mins"]

    total_captures = conn.execute(
        "SELECT COUNT(*) as count FROM captures"
    ).fetchone()["count"]

    avg_energy = conn.execute(
        "SELECT COALESCE(AVG(value), 0) as avg FROM energy_entries"
    ).fetchone()["avg"]

    conn.close()
    return {
        "total_sessions": total_sessions,
        "week_sessions": week_sessions,
        "total_minutes": round(total_minutes),
        "total_captures": total_captures,
        "avg_energy": round(avg_energy, 1) if avg_energy > 0 else None,
    }


init_db()
