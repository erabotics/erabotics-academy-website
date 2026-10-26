"""Endpoint logic. Each api/*.py file is a thin wrapper around one of these."""
import json
import time

from . import catalog, config, db, notify, security, validate
from .web import ApiError, get_cookie, read_body

ORDER_STATUSES = ('new', 'confirmed', 'delivered', 'cancelled')
MESSAGE_STATUSES = ('new', 'handled')
MESSAGE_KINDS = ('contact', 'adult_application')

PUBLIC_LIMIT = (5, 600)        # 5 submissions per 10 minutes per visitor
LOGIN_LIMIT = (5, 900)         # 5 failed logins per 15 minutes per visitor
LOGIN_GLOBAL_LIMIT = (50, 900)  # and 50 failures overall (slows distributed guessing)


def _require_origin(handler):
    if not security.origin_allowed(handler):
        raise ApiError(403, 'Request blocked.')


def _money(n):
    return f'{n:,} EGP'


# ---------------------------------------------------------------- public: order
def submit_order(handler):
    _require_origin(handler)
    data = read_body(handler)
    if validate.honeypot_filled(data):
        return 200, {'ok': True, 'ref': security.new_reference('ER')}, ()  # silently drop bots

    raw_items = data.get('items')
    if isinstance(raw_items, str):  # urlencoded fallback
        try:
            raw_items = json.loads(raw_items)
        except json.JSONDecodeError:
            raw_items = None
    if not isinstance(raw_items, list) or not raw_items:
        raise ApiError(400, 'Your cart is empty.')
    if len(raw_items) > 100:
        raise ApiError(400, 'Too many different items in one order.')

    # Prices, names and SKUs come from the server's catalog — never from the browser.
    products = catalog.products()
    lines, total = [], 0
    for item in raw_items:
        try:
            pid, qty = int(item.get('id')), int(item.get('qty'))
        except (AttributeError, TypeError, ValueError):
            raise ApiError(400, 'Your cart contains an invalid item.')
        if not 1 <= qty <= 999:
            raise ApiError(400, 'Quantities must be between 1 and 999.')
        product = products.get(pid)
        if not product:
            raise ApiError(409, 'A product in your cart is no longer available. Please review your cart.', {'id': pid})
        if not product.get('in'):
            raise ApiError(409, f'"{product["n"]}" is out of stock. Please remove it from your cart.', {'id': pid})
        subtotal = product['p'] * qty
        total += subtotal
        lines.append({'id': pid, 'sku': product.get('s', ''), 'name': product['n'], 'qty': qty, 'price': product['p'], 'subtotal': subtotal})

    fulfilment = validate.choice(data, 'fulfilment', 'Delivery option', ('Delivery', 'Pick up'), 'Delivery')
    delivery = fulfilment == 'Delivery'
    order = {
        'name': validate.text(data, 'name', 'Full name', 120),
        'phone': validate.phone(data),
        'email': validate.email(data),
        'fulfilment': fulfilment,
        'city': validate.text(data, 'city', 'City / Governorate', 80, required=delivery),
        'address': validate.text(data, 'address', 'Address', 240, required=delivery),
        'payment': validate.choice(data, 'payment', 'Payment method', ('Cash on delivery', 'InstaPay'), 'Cash on delivery'),
        'notes': validate.text(data, 'message', 'Notes', 1500, required=False, multiline=True),
    }
    ref = security.new_reference('ER')
    now = int(time.time())

    saved = False
    if db.configured():
        with db.connection() as conn:
            if security.rate_limited(conn, 'order', security.client_id(handler), *PUBLIC_LIMIT):
                raise ApiError(429, 'Too many orders from this connection. Please wait a few minutes or contact us on WhatsApp.')
            db.execute(conn, '''INSERT INTO orders (ref, created_at, status, name, phone, email, fulfilment, city, address,
                                payment, notes, items, total, updated_at) VALUES (?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (ref, now, order['name'], order['phone'], order['email'], order['fulfilment'], order['city'],
                        order['address'], order['payment'], order['notes'], json.dumps(lines), total, now))
        saved = True

    emailed = notify.email(f'New store order {ref} — {_money(total)}', {
        'order_id': ref,
        'order': '\n'.join(f"{l['qty']} × {l['name']} [SKU {l['sku']}] @ {_money(l['price'])} = {_money(l['subtotal'])}" for l in lines),
        'order_total': _money(total),
        **order,
    })
    if not (saved or emailed):
        raise ApiError(503, 'Orders are temporarily unavailable. Please contact us on WhatsApp: +20 101 539 7943.')
    return 201, {'ok': True, 'ref': ref, 'total': total, 'items': lines}, ()


# -------------------------------------------------------------- public: contact
def submit_contact(handler):
    _require_origin(handler)
    data = read_body(handler)
    if validate.honeypot_filled(data):
        return 200, {'ok': True}, ()

    kind = data.get('kind') or ('adult_application' if data.get('course') else 'contact')
    if kind not in MESSAGE_KINDS:
        raise ApiError(400, 'Invalid form.')
    name = validate.text(data, 'name', 'Full name', 120)
    email = validate.email(data, required=True)
    phone = validate.phone(data, required=(kind == 'adult_application'))
    if kind == 'contact':
        details = {
            'interest': validate.text(data, 'interest', 'Interest', 80, required=False),
            'message': validate.text(data, 'message', 'Message', 3000, multiline=True),
        }
    else:
        details = {
            'course': validate.text(data, 'course', 'Course', 80),
            'university': validate.text(data, 'university', 'University', 120),
            'college': validate.text(data, 'college', 'College / Faculty', 120),
            'department': validate.text(data, 'department', 'Department', 120),
            'year': validate.text(data, 'year', 'Year of study', 40),
            'message': validate.text(data, 'message', 'Message', 3000, required=False, multiline=True),
        }

    msg_id = security.new_reference('MSG')
    saved = False
    if db.configured():
        with db.connection() as conn:
            if security.rate_limited(conn, 'contact', security.client_id(handler), *PUBLIC_LIMIT):
                raise ApiError(429, 'Too many messages from this connection. Please wait a few minutes.')
            db.execute(conn, '''INSERT INTO messages (id, created_at, kind, status, name, email, phone, details)
                                VALUES (?, ?, ?, 'new', ?, ?, ?, ?)''',
                       (msg_id, int(time.time()), kind, name, email, phone, json.dumps(details)))
        saved = True

    fields = {'name': name, 'email': email, 'phone': phone, **details}
    subject = 'New adult course application — eraboticseg.com' if kind == 'adult_application' else 'New message from eraboticseg.com'
    emailed = notify.email(subject, fields)
    if kind == 'contact':
        notify.sheet(fields)
    if not (saved or emailed):
        raise ApiError(503, 'Messages are temporarily unavailable. Please email academy@eraboticseg.com.')
    return 201, {'ok': True, 'ref': msg_id}, ()


# ------------------------------------------------------------------- admin auth
def _admin_ready():
    if not db.configured() or not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD_HASH and config.SESSION_SECRET):
        raise ApiError(503, 'The admin area is not configured yet.')


def _session_payload(session):
    return {
        'ok': True,
        'user': session['username'],
        'idleTimeoutSeconds': security.idle_seconds(),
        'expiresAt': session['idle_expires_at'],
        'absoluteExpiresAt': session['expires_at'],
        'serverTime': int(time.time()),
    }


def require_admin(handler, conn, touch=True):
    session = security.load_session(conn, get_cookie(handler, security.COOKIE_NAME), touch=touch)
    if not session:
        raise ApiError(401, 'Your session has expired. Please sign in again.')
    return session


def admin_login(handler):
    _admin_ready()
    _require_origin(handler)
    data = read_body(handler, json_only=True)
    username = validate.text(data, 'username', 'Username', 80)
    password = data.get('password')
    if not isinstance(password, str) or not password or len(password) > 200:
        raise ApiError(400, 'Password is required.')
    client = security.client_id(handler)
    with db.connection() as conn:
        if (security.rate_limited(conn, 'login_fail', client, *LOGIN_LIMIT, record=False)
                or security.rate_limited(conn, 'login_fail', '*', *LOGIN_GLOBAL_LIMIT, record=False)):
            raise ApiError(429, 'Too many failed sign-in attempts. Please wait 15 minutes.')
        if not security.check_admin_credentials(username, password):
            security.record_event(conn, 'login_fail', client)
            security.record_event(conn, 'login_fail', '*')
            raise ApiError(401, 'Incorrect username or password.')
        security.clear_events(conn, 'login_fail', client)
        token = security.create_session(conn, username)
        session = security.load_session(conn, token)
    return 200, _session_payload(session), (security.session_cookie(token, security.max_seconds()),)


def admin_logout(handler):
    _require_origin(handler)
    if db.configured():
        with db.connection() as conn:
            security.end_session(conn, get_cookie(handler, security.COOKIE_NAME))
    return 200, {'ok': True}, (security.clear_cookie(),)


def admin_session(handler, extend):
    """GET: report the remaining time without extending it. POST: 'stay signed in'."""
    _admin_ready()
    if extend:
        _require_origin(handler)
    with db.connection() as conn:
        session = require_admin(handler, conn, touch=extend)
    return 200, _session_payload(session), ()


# ------------------------------------------------------------------ admin data
def admin_list(handler, table):
    _admin_ready()
    with db.connection() as conn:
        session = require_admin(handler, conn)
        rows = db.fetch_all(conn, f'SELECT * FROM {table} ORDER BY created_at DESC LIMIT 300')  # table is a fixed internal name
    key = 'items' if table == 'orders' else 'details'
    for r in rows:
        r[key] = json.loads(r[key] or ('[]' if key == 'items' else '{}'))
    return 200, {**_session_payload(session), 'rows': rows}, ()


def admin_update_status(handler, table):
    _admin_ready()
    _require_origin(handler)
    data = read_body(handler, json_only=True)
    statuses = ORDER_STATUSES if table == 'orders' else MESSAGE_STATUSES
    status = validate.choice(data, 'status', 'Status', statuses)
    ident = validate.text(data, 'ref' if table == 'orders' else 'id', 'Reference', 40)
    with db.connection() as conn:
        session = require_admin(handler, conn)
        if table == 'orders':
            cur = db.execute(conn, 'UPDATE orders SET status = ?, updated_at = ? WHERE ref = ?', (status, int(time.time()), ident))
        else:
            cur = db.execute(conn, 'UPDATE messages SET status = ? WHERE id = ?', (status, ident))
        if cur.rowcount == 0:
            raise ApiError(404, 'Not found.')
    return 200, {**_session_payload(session), 'status': status}, ()
