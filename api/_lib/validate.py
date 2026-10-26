"""Server-side validation — the browser's checks are a convenience, these are the rules."""
import re

from .web import ApiError

PHONE_RE = re.compile(r'^[0-9+ ()\-]{8,20}$')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$')
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def text(data, key, label, max_len, required=True, multiline=False):
    value = data.get(key, '')
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ApiError(400, f'{label} is invalid.')
    value = CONTROL_RE.sub('', value).strip()
    if not multiline:
        value = ' '.join(value.split())
    if required and not value:
        raise ApiError(400, f'{label} is required.', {'field': key})
    if len(value) > max_len:
        raise ApiError(400, f'{label} is too long (max {max_len} characters).', {'field': key})
    return value


def phone(data, key='phone', required=True):
    value = text(data, key, 'Phone number', 20, required)
    if value and not PHONE_RE.match(value):
        raise ApiError(400, 'Please enter a valid phone number.', {'field': key})
    return value


def email(data, key='email', required=False):
    value = text(data, key, 'Email', 254, required)
    if value and not EMAIL_RE.match(value):
        raise ApiError(400, 'Please enter a valid email address.', {'field': key})
    return value


def choice(data, key, label, options, default=None):
    value = data.get(key, default)
    if value not in options:
        raise ApiError(400, f'{label} is invalid.', {'field': key})
    return value


def honeypot_filled(data):
    """Bots fill every field; people never see this one."""
    return bool(str(data.get('_gotcha') or data.get('website') or '').strip())
