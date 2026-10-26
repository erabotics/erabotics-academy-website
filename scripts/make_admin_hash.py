"""Create the ADMIN_PASSWORD_HASH (or a SESSION_SECRET) for the environment variables.

    python scripts/make_admin_hash.py            # asks for a password, prints its hash
    python scripts/make_admin_hash.py --secret   # prints a new random SESSION_SECRET

The password is typed without being shown and is never written to disk.
Paste the printed value into Vercel → Settings → Environment Variables
(and into your local .env for testing).
"""
import getpass
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'api'))
from _lib.security import hash_password  # noqa: E402

MIN_LENGTH = 12

if '--secret' in sys.argv:
    print(secrets.token_urlsafe(48))
    sys.exit(0)

pw = getpass.getpass(f'New admin password (at least {MIN_LENGTH} characters): ')
if len(pw) < MIN_LENGTH:
    sys.exit(f'Password too short — use at least {MIN_LENGTH} characters.')
if getpass.getpass('Repeat password: ') != pw:
    sys.exit('Passwords do not match.')
print('\nADMIN_PASSWORD_HASH=' + hash_password(pw))
