# ERABOTICS website — security & privacy notes

This is an HTML/CSS/JavaScript website with a small Python backend, hosted on Vercel. It follows security best practices appropriate for its size. No website can be called "100% secure"; this document records what is in place, what depends on the hosting and form providers, and what would be needed if a backend is added.

## In the code (HTML / CSS / JavaScript)

| Area | What is done |
| --- | --- |
| Secrets | No API keys, passwords, tokens or credentials anywhere in the website code or git history. Server secrets (database, admin password hash, session secret, Formspree / Google Sheet URLs) are environment variables only — see the Backend section. |
| HTTPS | Every external resource, form endpoint and link uses `https://` (or `mailto:` / `tel:`). |
| Third parties | No analytics, trackers, ads, CDNs or external scripts. Fonts are self-hosted. The only JavaScript is the site's own four files (`main.js`, `cart.js`, `store.js`, `checkout.js`). |
| DOM safety | No `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval` or `document.write`. All dynamic content (store catalog, cart, chat answers) is built with `createElement` / `textContent`. |
| External links | Every link that opens a new tab uses `rel="noopener noreferrer"`. |
| Personal data | Contact, application and order details are sent over HTTPS to the site's own API (`/api/contact`, `/api/order`), which validates them, stores them in the database and forwards notifications server-side. They are never written to `localStorage`, `sessionStorage`, cookies or URL parameters, and forms are cleared after a successful send. |
| Browser storage | Only two non-personal items: the theme choice (`erabotics-theme`) and the cart's product list (`erabotics-cart`: product IDs, names, SKUs, prices). Cart data is validated on read and re-priced from the catalog at checkout, so tampering cannot lower a price. |
| URL parameters | Only Store search/filter/sort terms and a product ID — never personal data. |
| Forms | Honeypot field (`_gotcha`) against simple spam bots, browser-side checks for convenience, and full validation again on the server. |

## Configured on the hosting provider (Vercel) — not in the HTML

These are real HTTP response headers set in `vercel.json` and applied by Vercel. They are **not** duplicated as `<meta http-equiv>` tags, because meta tags do not provide the same protection (and several of these headers cannot be set that way at all).

- `Content-Security-Policy` — only the site's own scripts (plus the hash of the small inline theme script), styles, fonts and images; network requests and form posts only to the site itself (its own `/api`); no framing; no plugins. Google Forms, WhatsApp, Facebook and Instagram are ordinary links and are unaffected.
- `Strict-Transport-Security: max-age=63072000` (HTTPS for two years). Vercel also redirects HTTP to HTTPS and manages the TLS certificate.
- `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` (no clickjacking).
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (camera, microphone, location, payment etc. disabled), `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, `X-Permitted-Cross-Domain-Policies`.
- `/checkout`: `Cache-Control: no-store` and `X-Robots-Tag: noindex`.
- `.vercelignore` keeps `scripts/`, `.claude/` and these notes off the public site.
- The obsolete `X-XSS-Protection` header is deliberately not used.

If you add any new third-party service (analytics, chat, a payment provider), add its domain to the matching CSP directive in `vercel.json`, or the browser will block it. If you edit the inline theme script in a page's `<head>`, update its `sha256-` hash in the CSP.

### Recommended provider-side settings (not code)

- **GitHub:** make the repository private; enable 2-factor authentication for every account with access.
- **Vercel:** enable 2-factor authentication; keep the project's Git connection limited to this repository.
- **Formspree:** submissions now come from the server, so do not restrict the form by domain or add reCAPTCHA (that would block the server). Instead, because the old form URL is still visible in the public git history, create a new Formspree form and put its URL only in `FORMSPREE_ENDPOINT`.
- **Google Apps Script (contact sheet):** the old web-app URL is also in the git history — create a new deployment, put the new URL only in `SHEET_WEBHOOK_URL`, and have the script validate and length-limit incoming fields.
- **HSTS preload:** once every `*.eraboticseg.com` subdomain is confirmed to be HTTPS-only, the header can be extended with `includeSubDomains; preload` and submitted to hstspreload.org.

## Backend (Vercel Python functions in `api/`)

The site now has a small backend for orders, messages and a staff admin panel.

| Area | What is done |
| --- | --- |
| Secrets | All secrets live in environment variables — Vercel → Settings → Environment Variables in production, a git-ignored `.env` locally. `.env.example` documents the names with no values. `.env`, `.data/` and `scripts/supplier.local.json` are git-ignored and excluded from deployment. |
| Endpoints | `POST /api/order`, `POST /api/contact` (public); `/api/admin/login`, `logout`, `session`, `orders`, `messages` (staff). Shared code is in `api/_lib/`, which Vercel never publishes or exposes as endpoints. |
| Server-side validation | Every field is validated and length-limited on the server; request bodies are capped at 32 KB; only expected content types are accepted. |
| Order integrity | The browser sends only product IDs and quantities. Prices, names, SKUs and totals come from the server's catalog; unknown or out-of-stock products are rejected; the order reference is generated on the server. |
| SQL injection | All database queries are parameterised (`?` / `%s` placeholders). Table names are fixed in code, never taken from input. |
| Spam / abuse | Honeypot field; 5 submissions per 10 minutes per visitor; visitor IPs are stored only as a salted HMAC hash and rate-limit records are deleted after 24 hours. |
| CSRF | State-changing requests must come from the site's own Origin; admin endpoints accept JSON only (cannot be sent by a cross-site HTML form); the session cookie is `SameSite=Strict`. |
| Errors | Clients get generic messages; stack traces are logged server-side only. API responses are `Cache-Control: no-store`. |
| Notifications | Formspree and the Google Sheet are called from the server, using URLs stored in environment variables — they no longer appear in the website's source, and the browser CSP now allows network requests to the site itself only. |

### Admin sign-in and session time

- Password stored only as a **PBKDF2-SHA256 hash (600,000 iterations, random salt)** in `ADMIN_PASSWORD_HASH`; generate it with `python scripts/make_admin_hash.py` (minimum 12 characters). Comparisons are constant-time, and unknown usernames take the same time and get the same message as wrong passwords.
- **Brute-force protection:** sign-in is locked for 15 minutes after 5 failed attempts from one visitor, and after 50 failed attempts overall.
- **Session token:** 256-bit random value in a `__Host-era_admin` cookie that is `HttpOnly` (invisible to JavaScript), `Secure` (HTTPS only), `SameSite=Strict` and host-only. The database stores only the token's SHA-256 hash, so a database leak does not expose live sessions.
- **Session time:** signed out after **30 minutes without activity** (`SESSION_IDLE_MINUTES`) and **always after 8 hours** (`SESSION_MAX_HOURS`), enforced by the server on every request. The admin page shows a countdown, keeps the session alive while staff are working, asks "Still there?" 2 minutes before the limit, and clears customer data from the screen when the session ends. Signing out in one tab signs out all admin tabs; expired sessions are deleted from the database.
- A new session token is issued at every sign-in; signing out deletes the session server-side and clears the cookie.

### Still recommended

- Turn on 2-factor authentication for GitHub, Vercel and the database provider, and make the GitHub repository private.
- Use a long, unique admin password and rotate `SESSION_SECRET` / the password if staff with access leave.
- Enable Vercel Firewall / Bot protection rules for `/api/*` if spam increases (rate limiting here is per visitor, per database).
- A **privacy policy** describing what personal data is collected (names, phone numbers, addresses, messages), why, who can see it, and how long it is kept — and a routine for deleting old orders/messages.
- Database backups (Neon provides point-in-time restore) and access limited to the staff who need it.
- For online card payments in future: use the payment provider's hosted checkout so card data never touches ERABOTICS servers.
