"""
db.py — SQLite job cache for deduplication and tracking
"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            url         TEXT,
            match_score REAL,
            first_seen  TEXT,
            processed   INTEGER DEFAULT 0,
            applied     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS digests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at     TEXT,
            job_count   INTEGER,
            status      TEXT
        );
        """)
        # Migration: add applied column to existing DBs
        try:
            conn.execute("ALTER TABLE seen_jobs ADD COLUMN applied INTEGER DEFAULT 0")
        except Exception:
            pass  # column already exists


def is_seen(job_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM seen_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row is not None


def mark_seen(job: dict):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO seen_jobs
              (id, source, title, company, location, url, match_score, first_seen, processed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["id"],
            job.get("source", ""),
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("url", ""),
            job.get("match_score", 0.0),
            datetime.now().isoformat(),
            1
        ))


def update_job_score(job_id: str, score: float):
    with get_connection() as conn:
        conn.execute("UPDATE seen_jobs SET match_score = ? WHERE id = ?", (score, job_id))


def mark_applied(job_id: str, applied: bool = True):
    with get_connection() as conn:
        conn.execute(
            "UPDATE seen_jobs SET applied = ? WHERE id = ?",
            (1 if applied else 0, job_id)
        )


def log_digest(job_count: int, status: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO digests (sent_at, job_count, status) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), job_count, status)
        )


def get_recent_jobs(days: int = 7):
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM seen_jobs
            WHERE first_seen >= datetime('now', ?)
            ORDER BY match_score DESC
        """, (f"-{days} days",)).fetchall()
