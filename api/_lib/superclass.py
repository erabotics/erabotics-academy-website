"""SuperClass core: sign-in, sessions, roles, QR pairing. api/superclass.py routes here.

Roles
  admin         the platform owner (ERAbotics): sees every school and creates schools
  school_admin  runs one school (a branch such as "Manhattan"): its staff, classes, students
  teacher       runs Live Class for the classes assigned to them

How a teacher signs in:
  1. The smart board asks for a pairing request and shows a QR code plus a 4-digit PIN.
  2. The teacher's phone scans the QR, signs in with Google and types the PIN to approve.
  3. The board polls with its private secret and is signed in once (single use).

Only Google emails an admin has added can sign in. Sessions are random tokens kept
server-side (only their hash is stored) in an HttpOnly cookie, like the admin area.
Schools, classes, students and points live in sc_data.py.
"""
import hashlib
import hmac
import secrets
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request as UrlRequest, urlopen

from . import config, db, security, validate
from .web import ApiError, get_cookie, read_body

# Production: __Host- prefix (Secure, Path=/, no Domain). Local http development cannot use Secure cookies.
COOKIE_NAME = '__Host-sc_session' if config.ON_VERCEL else 'sc_session'
COOKIE_FLAGS = 'HttpOnly; Secure; SameSite=Strict' if config.ON_VERCEL else 'HttpOnly; SameSite=Strict'
PHONE_SESSION_SECONDS = 30 * 86400   # a teacher's phone stays signed in for a month
BOARD_SESSION_SECONDS = 12 * 3600    # a smart-board sign-in lasts one school day
PAIR_TTL_SECONDS = 120
PAIR_PIN_ATTEMPTS = 5
PAIR_START_LIMIT = (20, 600)         # 20 QR codes per 10 minutes per connection
LOGIN_LIMIT = (10, 900)              # 10 failed sign-ins per 15 minutes per connection

ROLES = ('admin', 'school_admin', 'teacher')


# ---------------------------------------------------------------- small helpers
def require_origin(handler):
    if not security.origin_allowed(handler):
        raise ApiError(403, 'Request blocked.')


def ready():
    if not db.configured():
        raise ApiError(503, 'SuperClass sign-in is not set up yet.')


def new_id():
    return secrets.token_hex(8)


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _cookie(token, max_age):
    return f'{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; {COOKIE_FLAGS}'


def _clear_cookie():
    return _cookie('', 0)


def public_user(user):
    return {
        'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role'],
        'schoolId': user.get('school_id'), 'schoolName': user.get('school_name'),
        'status': user.get('status', 'active'), 'lastLogin': user.get('last_login'),
    }


def audit(conn, user, action, detail='', school_id=None):
    """Record who did what (shown to admins in the Activity log)."""
    db.execute(conn, 'INSERT INTO sc_audit (id, at, school_id, user_id, user_name, action, detail) VALUES (?, ?, ?, ?, ?, ?, ?)',
               (new_id(), int(time.time()), school_id if school_id is not None else (user or {}).get('school_id'),
                (user or {}).get('id'), (user or {}).get('name') or 'System', action, detail[:300]))


USER_SELECT = '''SELECT u.id, u.name, u.email, u.role, u.school_id, u.status, u.last_login,
                        sch.name AS school_name, sch.status AS school_status
                 FROM sc_users u LEFT JOIN sc_schools sch ON sch.id = u.school_id'''


def _check_active(user):
    if user['status'] != 'active':
        raise ApiError(403, 'Your account is paused. Ask your admin.')
    if user['role'] != 'admin' and user.get('school_id') and user.get('school_status') != 'active':
        raise ApiError(403, 'Your school is paused. Ask your admin.')


def _new_session(conn, user_id, kind, seconds):
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    db.execute(conn, 'DELETE FROM sc_sessions WHERE expires_at < ?', (now,))
    db.execute(conn, 'INSERT INTO sc_sessions (token_hash, user_id, kind, created_at, expires_at) VALUES (?, ?, ?, ?, ?)',
               (_hash(token), user_id, kind, now, now + seconds))
    db.execute(conn, 'UPDATE sc_users SET last_login = ? WHERE id = ?', (now, user_id))
    return token


def current_user(handler, conn):
    token = get_cookie(handler, COOKIE_NAME)
    if not token or len(token) > 100:
        raise ApiError(401, 'Please sign in.')
    row = db.fetch_one(conn, USER_SELECT.replace('FROM sc_users u', 'FROM sc_sessions s JOIN sc_users u ON u.id = s.user_id')
                       + ' WHERE s.token_hash = ? AND s.expires_at > ?', (_hash(token), int(time.time())))
    if not row:
        raise ApiError(401, 'Please sign in.')
    _check_active(row)
    return row


def _user_for_email(conn, email):
    """The account for a verified email. The configured owner email is created on first use."""
    email = email.strip().lower()
    row = db.fetch_one(conn, USER_SELECT + ' WHERE u.email = ?', (email,))
    if row:
        _check_active(row)
        return row
    if config.SUPERCLASS_ADMIN_EMAIL and email == config.SUPERCLASS_ADMIN_EMAIL:
        uid = new_id()
        db.execute(conn, 'INSERT INTO sc_users (id, email, name, role, created_at) VALUES (?, ?, ?, ?, ?)',
                   (uid, email, 'Admin', 'admin', int(time.time())))
        return db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (uid,))
    return None


# ---------------------------------------------------------------- Google sign-in
class _Response:
    def __init__(self, status, headers, data):
        self.status, self.headers, self.data = status, headers, data


def _urllib_request(url, method='GET', body=None, headers=None, timeout=8, **_):
    """Minimal HTTP transport for google-auth (avoids pulling in `requests`)."""
    with urlopen(UrlRequest(url, data=body, headers=headers or {}, method=method), timeout=timeout) as r:
        return _Response(r.status, dict(r.headers), r.read())


def _verify_google(credential):
    from google.oauth2 import id_token  # installed from requirements.txt on Vercel
    info = id_token.verify_oauth2_token(credential, _urllib_request, config.GOOGLE_CLIENT_ID, clock_skew_in_seconds=10)
    if not info.get('email') or info.get('email_verified') is not True:
        raise ValueError('Email not verified')
    return info['email']


def get_config(handler, query):
    return 200, {'ok': True, 'googleClientId': config.GOOGLE_CLIENT_ID or None, 'devLogin': config.SUPERCLASS_DEV_LOGIN}, ()


def google_login(handler, query):
    ready()
    require_origin(handler)
    if not config.GOOGLE_CLIENT_ID:
        raise ApiError(503, 'Google sign-in is not set up yet.')
    data = read_body(handler, json_only=True)
    credential = data.get('credential')
    if not isinstance(credential, str) or not credential or len(credential) > 4000:
        raise ApiError(400, 'Sign-in failed. Try again.')
    client = security.client_id(handler)
    with db.connection() as conn:
        if security.rate_limited(conn, 'sc_login_fail', client, *LOGIN_LIMIT, record=False):
            raise ApiError(429, 'Too many attempts. Wait a few minutes and try again.')
        try:
            email = _verify_google(credential)
        except Exception:
            security.record_event(conn, 'sc_login_fail', client)
            raise ApiError(401, 'Google sign-in failed. Try again.')
        try:
            user = _user_for_email(conn, email)
        except ApiError:
            security.record_event(conn, 'sc_login_fail', client)
            raise
        if not user:
            security.record_event(conn, 'sc_login_fail', client)
            raise ApiError(403, f'{email} is not registered. Ask your admin to add it.')
        token = _new_session(conn, user['id'], 'phone', PHONE_SESSION_SECONDS)
        audit(conn, user, 'sign_in', 'Google (phone)')
    return 200, {'ok': True, 'user': public_user(user)}, (_cookie(token, PHONE_SESSION_SECONDS),)


def dev_login(handler, query):
    """Local testing only (SUPERCLASS_DEV_LOGIN=1, never on Vercel): sign in by email, no Google."""
    if not config.SUPERCLASS_DEV_LOGIN:
        raise ApiError(404, 'Not found.')
    ready()
    data = read_body(handler, json_only=True)
    email = validate.text(data, 'email', 'Email', 150)
    with db.connection() as conn:
        user = _user_for_email(conn, email)
        if not user:
            raise ApiError(403, 'No account with that email.')
        token = _new_session(conn, user['id'], 'phone', PHONE_SESSION_SECONDS)
    return 200, {'ok': True, 'user': public_user(user)}, (_cookie(token, PHONE_SESSION_SECONDS),)


def me(handler, query):
    ready()
    with db.connection() as conn:
        user = current_user(handler, conn)
    return 200, {'ok': True, 'user': public_user(user)}, ()


def logout(handler, query):
    require_origin(handler)
    if db.configured():
        token = get_cookie(handler, COOKIE_NAME)
        if token:
            with db.connection() as conn:
                db.execute(conn, 'DELETE FROM sc_sessions WHERE token_hash = ?', (_hash(token),))
    return 200, {'ok': True}, (_clear_cookie(),)


# ---------------------------------------------------------------- smart-board QR pairing
def pair_start(handler, query):
    ready()
    require_origin(handler)
    client = security.client_id(handler)
    now = int(time.time())
    code = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(24)
    pin = f'{secrets.randbelow(10000):04d}'
    with db.connection() as conn:
        if security.rate_limited(conn, 'sc_pair', client, *PAIR_START_LIMIT):
            raise ApiError(429, 'Too many requests. Wait a moment.')
        db.execute(conn, 'DELETE FROM sc_pairs WHERE expires_at < ?', (now,))
        db.execute(conn, 'INSERT INTO sc_pairs (code, secret_hash, pin, expires_at) VALUES (?, ?, ?, ?)',
                   (code, _hash(secret), pin, now + PAIR_TTL_SECONDS))
    # Send the lifetime, not a timestamp: the board's clock and the server's may differ
    return 201, {'ok': True, 'code': code, 'secret': secret, 'pin': pin, 'expiresIn': PAIR_TTL_SECONDS}, ()


def pair_status(handler, query):
    ready()
    code = (query.get('code') or [''])[0][:80]
    secret = (query.get('secret') or [''])[0][:80]
    now = int(time.time())
    with db.connection() as conn:
        pair = db.fetch_one(conn, 'SELECT * FROM sc_pairs WHERE code = ?', (code,))
        # The code is visible in the QR, so a wrong secret must never be able to cancel the request
        if not pair or not hmac.compare_digest(pair['secret_hash'], _hash(secret)):
            return 200, {'ok': True, 'status': 'expired'}, ()
        if pair['expires_at'] < now:
            db.execute(conn, 'DELETE FROM sc_pairs WHERE code = ?', (code,))
            return 200, {'ok': True, 'status': 'expired'}, ()
        if not pair['user_id']:
            return 200, {'ok': True, 'status': 'pending'}, ()
        db.execute(conn, 'DELETE FROM sc_pairs WHERE code = ?', (code,))  # single use
        user = db.fetch_one(conn, USER_SELECT + ' WHERE u.id = ?', (pair['user_id'],))
        if not user or user['status'] != 'active':
            return 200, {'ok': True, 'status': 'expired'}, ()
        token = _new_session(conn, user['id'], 'board', BOARD_SESSION_SECONDS)
        audit(conn, user, 'sign_in', 'Smart board (QR)')
    return 200, {'ok': True, 'status': 'approved', 'user': public_user(user)}, (_cookie(token, BOARD_SESSION_SECONDS),)


def pair_approve(handler, query):
    ready()
    require_origin(handler)
    data = read_body(handler, json_only=True)
    code = validate.text(data, 'code', 'Code', 80)
    pin = data.get('pin')
    if not isinstance(pin, str):
        raise ApiError(400, 'Type the code shown on the board.')
    with db.connection() as conn:
        user = current_user(handler, conn)
        pair = db.fetch_one(conn, 'SELECT * FROM sc_pairs WHERE code = ?', (code,))
        if not pair or pair['expires_at'] < int(time.time()):
            raise ApiError(410, 'This QR code has expired. Scan the new one on the board.')
        if pair['attempts'] >= PAIR_PIN_ATTEMPTS:
            db.execute(conn, 'DELETE FROM sc_pairs WHERE code = ?', (code,))
            raise ApiError(429, 'Too many wrong codes. Scan the new QR on the board.')
        if not hmac.compare_digest(pin.strip(), pair['pin']):
            db.execute(conn, 'UPDATE sc_pairs SET attempts = attempts + 1 WHERE code = ?', (code,))
            raise ApiError(400, 'That code does not match the one on the board.')
        db.execute(conn, 'UPDATE sc_pairs SET user_id = ? WHERE code = ?', (user['id'], code))
    return 200, {'ok': True, 'name': user['name']}, ()


# ---------------------------------------------------------------- router
CORE_ROUTES = {
    ('GET', 'config'): get_config,
    ('GET', 'me'): me,
    ('GET', 'pair/status'): pair_status,
    ('POST', 'google'): google_login,
    ('POST', 'dev-login'): dev_login,
    ('POST', 'logout'): logout,
    ('POST', 'pair/start'): pair_start,
    ('POST', 'pair/approve'): pair_approve,
}


def dispatch(handler, method):
    from . import sc_data  # schools, classes, students, points (imports this module)
    query = parse_qs(urlsplit(handler.path).query)
    route = (query.get('r') or [''])[0]
    fn = CORE_ROUTES.get((method, route)) or sc_data.ROUTES.get((method, route))
    if not fn:
        raise ApiError(404, 'Not found.')
    return fn(handler, query)
