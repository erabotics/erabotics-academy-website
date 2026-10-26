"""Passwords, admin sessions, rate limiting and request-origin checks."""
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

from . import config, db

# ---------- Passwords (PBKDF2-HMAC-SHA256) ----------
PBKDF2_ITERATIONS = 600_000


def hash_password(password, iterations=PBKDF2_ITERATIONS):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    b64 = lambda b: base64.b64encode(b).decode('ascii')
    return f'pbkdf2_sha256${iterations}${b64(salt)}${b64(digest)}'


def verify_password(password, stored):
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, int(iterations))
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


# A fixed dummy hash so failed logins for unknown users take the same time.
_DUMMY_HASH = 'pbkdf2_sha256$600000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='


def check_admin_credentials(username, password):
    if not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD_HASH):
        return False
    user_ok = hmac.compare_digest(username.encode('utf-8'), config.ADMIN_USERNAME.encode('utf-8'))
    pass_ok = verify_password(password, config.ADMIN_PASSWORD_HASH if user_ok else _DUMMY_HASH)
    return user_ok and pass_ok


# ---------- Sessions ----------
COOKIE_NAME = '__Host-era_admin'


def _token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def idle_seconds():
    return max(1, config.SESSION_IDLE_MINUTES) * 60


def max_seconds():
    return max(1, config.SESSION_MAX_HOURS) * 3600


def create_session(conn, username):
    """Start a new session; returns the raw token (only its hash is stored)."""
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    db.execute(conn, 'DELETE FROM admin_sessions WHERE expires_at < ? OR last_seen < ?',
               (now, now - idle_seconds()))
    db.execute(conn, 'INSERT INTO admin_sessions (token_hash, username, created_at, last_seen, expires_at) VALUES (?, ?, ?, ?, ?)',
               (_token_hash(token), username, now, now, now + max_seconds()))
    return token


def load_session(conn, token, touch=True):
    """Return the session if it is still valid (idle and absolute limits), else None."""
    if not token or len(token) > 100:
        return None
    now = int(time.time())
    row = db.fetch_one(conn, 'SELECT * FROM admin_sessions WHERE token_hash = ?', (_token_hash(token),))
    if not row:
        return None
    if row['expires_at'] <= now or row['last_seen'] + idle_seconds() <= now:
        db.execute(conn, 'DELETE FROM admin_sessions WHERE token_hash = ?', (row['token_hash'],))
        return None
    if touch:
        db.execute(conn, 'UPDATE admin_sessions SET last_seen = ? WHERE token_hash = ?', (now, row['token_hash']))
        row['last_seen'] = now
    row['idle_expires_at'] = min(row['last_seen'] + idle_seconds(), row['expires_at'])
    return row


def end_session(conn, token):
    if token:
        db.execute(conn, 'DELETE FROM admin_sessions WHERE token_hash = ?', (_token_hash(token),))


def session_cookie(token, max_age):
    # __Host- prefix: Secure, Path=/ and no Domain, so subdomains cannot set or read it.
    return (f'{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; '
            'HttpOnly; Secure; SameSite=Strict')


def clear_cookie():
    return f'{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict'


# ---------- Rate limiting ----------
def client_id(handler):
    """A salted hash of the caller's IP — raw IP addresses are never stored."""
    if config.ON_VERCEL:
        ip = handler.headers.get('x-real-ip') or (handler.headers.get('x-forwarded-for') or '').split(',')[0]
    else:
        ip = handler.client_address[0]
    salt = config.SESSION_SECRET or 'local-development-only'
    return hmac.new(salt.encode(), ip.strip().encode(), hashlib.sha256).hexdigest()[:32]


def rate_limited(conn, bucket, client, limit, window_seconds, record=True):
    """True if `client` already made `limit` events in `bucket` within the window."""
    now = int(time.time())
    db.execute(conn, 'DELETE FROM rate_events WHERE at < ?', (now - 86400,))
    row = db.fetch_one(conn, 'SELECT COUNT(*) AS n FROM rate_events WHERE bucket = ? AND client = ? AND at > ?',
                       (bucket, client, now - window_seconds))
    if row and row['n'] >= limit:
        return True
    if record:
        db.execute(conn, 'INSERT INTO rate_events (bucket, client, at) VALUES (?, ?, ?)', (bucket, client, now))
    return False


def record_event(conn, bucket, client):
    db.execute(conn, 'INSERT INTO rate_events (bucket, client, at) VALUES (?, ?, ?)', (bucket, client, int(time.time())))


def clear_events(conn, bucket, client):
    db.execute(conn, 'DELETE FROM rate_events WHERE bucket = ? AND client = ?', (bucket, client))


# ---------- Origin check (CSRF defence for state-changing requests) ----------
def origin_allowed(handler):
    origin = (handler.headers.get('Origin') or '').rstrip('/')
    if not origin:
        # Browsers always send Origin on cross-site POSTs; a missing header means
        # a same-origin navigation or a non-browser client.
        return True
    if origin in config.ALLOWED_ORIGINS:
        return True
    host = (handler.headers.get('x-forwarded-host') or handler.headers.get('Host') or '').lower()
    return urlsplit(origin).netloc.lower() == host


def new_reference(prefix):
    alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # no 0/O/1/I confusion
    stamp = time.strftime('%y%m%d', time.gmtime())
    return f'{prefix}-{stamp}-' + ''.join(secrets.choice(alphabet) for _ in range(6))
