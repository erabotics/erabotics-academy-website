"""Settings, read from environment variables.

On Vercel these are set in Project Settings → Environment Variables.
Locally they are read from a git-ignored .env file in the project root.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_dotenv():
    """Minimal .env reader for local development (never used on Vercel)."""
    path = os.path.join(ROOT, '.env')
    if os.environ.get('VERCEL') or not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


_load_dotenv()


def env(name, default=''):
    return os.environ.get(name, default).strip()


def env_int(name, default):
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


ON_VERCEL = bool(os.environ.get('VERCEL'))

# Storage: postgres://… in production; sqlite:///path for local development.
DATABASE_URL = env('DATABASE_URL') or env('POSTGRES_URL')

# Admin login. The password is never stored — only a PBKDF2 hash
# (generate it with: python scripts/make_admin_hash.py).
ADMIN_USERNAME = env('ADMIN_USERNAME')
ADMIN_PASSWORD_HASH = env('ADMIN_PASSWORD_HASH')

# Secret used to hash IP addresses for rate limiting (never store raw IPs).
SESSION_SECRET = env('SESSION_SECRET')

# Session lifetime
SESSION_IDLE_MINUTES = env_int('SESSION_IDLE_MINUTES', 30)
SESSION_MAX_HOURS = env_int('SESSION_MAX_HOURS', 8)

# Optional forwarding of submissions by email / to the contact sheet.
FORMSPREE_ENDPOINT = env('FORMSPREE_ENDPOINT')
SHEET_WEBHOOK_URL = env('SHEET_WEBHOOK_URL')

# Extra allowed origins for state-changing requests (comma-separated).
ALLOWED_ORIGINS = [o.strip().rstrip('/') for o in env('ALLOWED_ORIGINS').split(',') if o.strip()]

CATALOG_PATH = os.path.join(ROOT, 'assets', 'data', 'catalog.json')
