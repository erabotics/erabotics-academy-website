# ERABOTICS backend — setup

The backend is a set of small Python functions in `api/` that Vercel runs automatically (no server to manage). Shared code is in `api/_lib/`.

| Endpoint | Who | What |
| --- | --- | --- |
| `POST /api/order` | Public | Places a store order (prices checked on the server) |
| `POST /api/contact` | Public | Contact messages and adult-course applications |
| `POST /api/admin/login` · `logout` | Staff | Sign in / out |
| `GET`/`POST /api/admin/session` | Staff | Time left / stay signed in |
| `GET`/`PATCH /api/admin/orders` · `messages` | Staff | List / change status |
| `/admin` | Staff | The admin panel page |

## 1. Database (one time)

In Vercel: **Storage → Create Database → Neon (Postgres)** and connect it to the `erabotics-academy` project for **Production** and **Preview**. Vercel adds `DATABASE_URL` automatically. Tables are created on first use.

## 2. Environment variables (one time)

Vercel → `erabotics-academy` → **Settings → Environment Variables** (Production and Preview). See `.env.example` for every name.

| Name | Value |
| --- | --- |
| `ADMIN_USERNAME` | The staff sign-in name |
| `ADMIN_PASSWORD_HASH` | Run `python scripts/make_admin_hash.py` on your computer, type a strong password (12+ characters), paste the printed hash |
| `SESSION_SECRET` | Run `python scripts/make_admin_hash.py --secret` and paste the result |
| `SESSION_IDLE_MINUTES` | `30` |
| `SESSION_MAX_HOURS` | `8` |
| `FORMSPREE_ENDPOINT` | A **new** Formspree form URL (optional — email notifications) |
| `SHEET_WEBHOOK_URL` | A **new** Google Apps Script deployment URL (optional — contact sheet) |

Mark `ADMIN_PASSWORD_HASH`, `SESSION_SECRET`, `FORMSPREE_ENDPOINT` and `SHEET_WEBHOOK_URL` as **Sensitive**. After changing variables, redeploy.

If the database is not connected yet, orders and messages are still accepted as long as `FORMSPREE_ENDPOINT` is set (email only), and the admin panel reports that it is not configured.

## 3. Local development

```bash
cp .env.example .env        # then fill in test values
python scripts/dev_server.py
```

Opens on http://localhost:5173 with the site, the API and `/admin`. Local data is stored in `.data/local.db` (git-ignored).
