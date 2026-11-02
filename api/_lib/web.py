"""Small helpers shared by the api/ handlers: parsing requests, sending
responses with safe headers, and turning errors into JSON."""
import json
import traceback
from urllib.parse import parse_qs

MAX_BODY = 32 * 1024  # bytes — forms and orders are small


class ApiError(Exception):
    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


def read_body(handler, json_only=False, max_body=MAX_BODY):
    """Parse a JSON (or, for public forms, urlencoded) body with a size limit."""
    try:
        length = int(handler.headers.get('Content-Length') or 0)
    except ValueError:
        raise ApiError(400, 'Invalid request.')
    if length <= 0:
        raise ApiError(400, 'Empty request.')
    if length > max_body:
        raise ApiError(413, 'Request is too large.')
    raw = handler.rfile.read(length)
    ctype = (handler.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if ctype == 'application/json':
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, 'Invalid JSON.')
        if not isinstance(data, dict):
            raise ApiError(400, 'Invalid request.')
        return data
    if not json_only and ctype == 'application/x-www-form-urlencoded':
        try:
            return {k: v[0] for k, v in parse_qs(raw.decode('utf-8'), max_num_fields=60).items()}
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, 'Invalid form data.')
    raise ApiError(415, 'Unsupported content type.')


def get_cookie(handler, name):
    """Read one cookie by name. Parsed by hand: other scripts (for example Google's sign-in
    adds `g_state={"i_l":0,...}`) set cookies with quotes and commas, and SimpleCookie
    then drops every cookie in the header, including ours."""
    for part in (handler.headers.get('Cookie') or '').split(';'):
        key, sep, value = part.strip().partition('=')
        if sep and key == name:
            return value.strip().strip('"')
    return None


def send_json(handler, status, payload, cookies=()):
    body = json.dumps(payload).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    # API responses may contain personal data: never cache them anywhere.
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Referrer-Policy', 'no-referrer')
    for cookie in cookies:
        handler.send_header('Set-Cookie', cookie)
    handler.end_headers()
    handler.wfile.write(body)


def run(handler, fn):
    """Run an endpoint function, converting errors into safe JSON responses."""
    try:
        status, payload, cookies = fn()
        send_json(handler, status, payload, cookies)
    except ApiError as e:
        send_json(handler, e.status, {'ok': False, 'error': e.message, **e.extra})
    except Exception:
        # Log the stack trace server-side only; never leak internals to the client.
        traceback.print_exc()
        send_json(handler, 500, {'ok': False, 'error': 'Something went wrong. Please try again, or contact us on WhatsApp.'})


def method_not_allowed(handler, allowed):
    handler.send_response(405)
    handler.send_header('Allow', allowed)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', '0')
    handler.end_headers()
