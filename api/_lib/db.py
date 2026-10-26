"""Database access: Postgres in production, SQLite for local development.

Every query is parameterised (placeholders, never string formatting), which
prevents SQL injection. SQL is written with `?` placeholders and converted
to `%s` for Postgres.
"""
import os
import sqlite3
from contextlib import contextmanager

from . import config
from .web import ApiError

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS orders (
        ref TEXT PRIMARY KEY,
        created_at BIGINT NOT NULL,
        status TEXT NOT NULL,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        fulfilment TEXT NOT NULL,
        city TEXT,
        address TEXT,
        payment TEXT NOT NULL,
        notes TEXT,
        items TEXT NOT NULL,
        total INTEGER NOT NULL,
        updated_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        created_at BIGINT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        details TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS admin_sessions (
        token_hash TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        created_at BIGINT NOT NULL,
        last_seen BIGINT NOT NULL,
        expires_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS rate_events (
        bucket TEXT NOT NULL,
        client TEXT NOT NULL,
        at BIGINT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS rate_events_lookup ON rate_events (bucket, client, at)",
    "CREATE INDEX IF NOT EXISTS orders_created ON orders (created_at)",
    "CREATE INDEX IF NOT EXISTS messages_created ON messages (created_at)",
]

_initialised = False


def configured():
    return bool(config.DATABASE_URL)


def _is_postgres():
    return config.DATABASE_URL.startswith(('postgres://', 'postgresql://'))


def _connect():
    url = config.DATABASE_URL
    if _is_postgres():
        import psycopg  # installed from requirements.txt on Vercel
        return psycopg.connect(url, connect_timeout=8)
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///'):]
        if not os.path.isabs(path):
            path = os.path.join(config.ROOT, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return sqlite3.connect(path)
    raise RuntimeError('DATABASE_URL must start with postgres:// or sqlite:///')


def _sql(query):
    return query.replace('?', '%s') if _is_postgres() else query


@contextmanager
def connection():
    global _initialised
    conn = _connect()
    try:
        if not _initialised:
            cur = conn.cursor()
            for stmt in SCHEMA:
                cur.execute(stmt)
            conn.commit()
            _initialised = True
        yield conn
        conn.commit()
    except ApiError:
        # A deliberate error response (wrong password, expired session …) still
        # keeps what was recorded: failed-login counters, expired-session cleanup.
        conn.commit()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(conn, query, params=()):
    cur = conn.cursor()
    cur.execute(_sql(query), tuple(params))
    return cur


def fetch_all(conn, query, params=()):
    cur = execute(conn, query, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(conn, query, params=()):
    rows = fetch_all(conn, query, params)
    return rows[0] if rows else None
