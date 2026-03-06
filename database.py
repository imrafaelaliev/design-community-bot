import os
import sqlite3
from typing import Optional, Tuple

DB_PATH = os.getenv("SQLITE_DB_PATH", "subscriptions.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                subscription_status TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        conn.commit()


def update_subscription(
    telegram_user_id: int,
    subscription_status: str,
    expires_at: Optional[str],
) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_user_id, subscription_status, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                subscription_status = excluded.subscription_status,
                expires_at = excluded.expires_at
            """,
            (telegram_user_id, subscription_status, expires_at),
        )
        conn.commit()


def get_subscription(telegram_user_id: int) -> Optional[Tuple[int, str, Optional[str]]]:
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT telegram_user_id, subscription_status, expires_at
            FROM users
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        ).fetchone()

    if row is None:
        return None
    return row["telegram_user_id"], row["subscription_status"], row["expires_at"]
