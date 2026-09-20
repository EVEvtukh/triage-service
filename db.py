"""
db.py — работа с SQLite (журнал/аудит обращений).

Таблица tickets хранит и вход, и результат обработки — по ней
можно проверять качество модели и разбирать инциденты.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "tickets.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            client_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            text TEXT NOT NULL,
            category TEXT,
            confidence TEXT,
            escalate INTEGER,
            draft_reply TEXT,
            error TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def insert_ticket(client_id: str, channel: str, text: str,
                   category: str | None, confidence: str | None,
                   escalate: bool, draft_reply: str | None,
                   error: str | None = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO tickets
            (created_at, client_id, channel, text, category, confidence,
             escalate, draft_reply, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            client_id,
            channel,
            text,
            category,
            confidence,
            int(escalate),
            draft_reply,
            error,
        ),
    )
    conn.commit()
    ticket_id = cur.lastrowid
    conn.close()
    return ticket_id


def fetch_all_tickets(limit: int = 100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tickets ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
