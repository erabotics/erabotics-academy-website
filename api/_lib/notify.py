"""Optional forwarding of submissions (email via Formspree, contact sheet via
Google Apps Script). Endpoints come from environment variables, so they are
no longer visible in the website's source."""
import json
import urllib.parse
import urllib.request

from . import config


def _post(url, payload, as_json=True):
    if not url.startswith('https://'):
        return False
    data = json.dumps(payload).encode('utf-8') if as_json else urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST', headers={
        'Content-Type': 'application/json' if as_json else 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'User-Agent': 'ERABOTICS-backend/1.0',
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def email(subject, fields):
    """Send a notification email through Formspree. Returns True if delivered."""
    if not config.FORMSPREE_ENDPOINT:
        return False
    return _post(config.FORMSPREE_ENDPOINT, {'_subject': subject, **fields})


def sheet(fields):
    if not config.SHEET_WEBHOOK_URL:
        return False
    return _post(config.SHEET_WEBHOOK_URL, fields, as_json=False)
