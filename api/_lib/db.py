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
    # SuperClass: teacher accounts (Google email), sign-in sessions, smart-board QR requests
    """CREATE TABLE IF NOT EXISTS sc_users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sc_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        created_at BIGINT NOT NULL,
        expires_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sc_pairs (
        code TEXT PRIMARY KEY,
        secret_hash TEXT NOT NULL,
        pin TEXT NOT NULL,
        user_id TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        expires_at BIGINT NOT NULL
    )""",
    # SuperClass schools (branches such as "Manhattan"): each has its own staff, classes and students
    """CREATE TABLE IF NOT EXISTS sc_schools (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        settings TEXT NOT NULL DEFAULT '{}',
        created_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sc_classes (
        id TEXT PRIMARY KEY,
        school_id TEXT NOT NULL,
        name TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT '',
        schedule TEXT NOT NULL DEFAULT '',
        archived INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sc_class_teachers (
        class_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        PRIMARY KEY (class_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS sc_students (
        id TEXT PRIMARY KEY,
        school_id TEXT NOT NULL,
        name TEXT NOT NULL,
        photo TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sc_enrollments (
        class_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        PRIMARY KEY (class_id, student_id)
    )""",
    """CREATE TABLE IF NOT EXISTS sc_points (
        id TEXT PRIMARY KEY,
        school_id TEXT NOT NULL,
        class_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        delta INTEGER NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        by_user TEXT NOT NULL,
        at BIGINT NOT NULL,
        undone INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS sc_audit (
        id TEXT PRIMARY KEY,
        at BIGINT NOT NULL,
        school_id TEXT,
        user_id TEXT,
        user_name TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS sc_points_class ON sc_points (class_id, student_id)",
    "CREATE INDEX IF NOT EXISTS sc_points_school ON sc_points (school_id, at)",
    "CREATE INDEX IF NOT EXISTS sc_audit_school ON sc_audit (school_id, at)",
    "CREATE INDEX IF NOT EXISTS sc_students_school ON sc_students (school_id)",
    "CREATE INDEX IF NOT EXISTS sc_classes_school ON sc_classes (school_id)",
    "CREATE INDEX IF NOT EXISTS rate_events_lookup ON rate_events (bucket, client, at)",
    "CREATE INDEX IF NOT EXISTS orders_created ON orders (created_at)",
    "CREATE INDEX IF NOT EXISTS messages_created ON messages (created_at)",
]

# Columns added after a table first shipped (CREATE TABLE IF NOT EXISTS never alters a live table)
COLUMN_MIGRATIONS = [
    ('sc_users', 'school_id', 'TEXT'),
    ('sc_users', 'status', "TEXT NOT NULL DEFAULT 'active'"),
    ('sc_users', 'last_login', 'BIGINT'),
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


def _has_column(cur, table, column):
    if _is_postgres():
        cur.execute('SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s', (table, column))
        return cur.fetchone() is not None
    cur.execute(f'PRAGMA table_info({table})')
    return any(row[1] == column for row in cur.fetchall())


@contextmanager
def connection():
    global _initialised
    conn = _connect()
    try:
        if not _initialised:
            cur = conn.cursor()
            for stmt in SCHEMA:
                cur.execute(stmt)
            for table, column, definition in COLUMN_MIGRATIONS:
                if not _has_column(cur, table, column):
                    cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')  # fixed internal names
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
