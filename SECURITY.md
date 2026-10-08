# ERABOTICS website — security & privacy notes

This is a static HTML/CSS/JavaScript website hosted on Vercel. It follows security best practices appropriate for a static frontend. No website can be called "100% secure"; this document records what is in place, what depends on the hosting and form providers, and what would be needed if a backend is added.

## In the code (HTML / CSS / JavaScript)

| Area | What is done |
| --- | --- |
| Secrets | No API keys, passwords, tokens or credentials anywhere in the code or git history. The only endpoints are the public Formspree form URL and the Google Apps Script web-app URL, which are designed to be public. The supplier catalog address used by `scripts/sync_catalog.py` lives in a git-ignored local file and is never published. |
| HTTPS | Every external resource, form endpoint and link uses `https://` (or `mailto:` / `tel:`). |
| Third parties | No analytics, trackers, ads, CDNs or external scripts. Fonts are self-hosted. The only JavaScript is the site's own four files (`main.js`, `cart.js`, `store.js`, `checkout.js`). |
| DOM safety | No `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval` or `document.write`. All dynamic content (store catalog, cart, chat answers) is built with `createElement` / `textContent`. |
| External links | Every link that opens a new tab uses `rel="noopener noreferrer"`. |
| Personal data | Contact, application and order details are sent directly to Formspree (and, for the contact form only, the ERABOTICS Google Sheet) over HTTPS on submit. They are never written to `localStorage`, `sessionStorage`, cookies or URL parameters, and the form is cleared after a successful send. |
| Browser storage | Only two non-personal items: the theme choice (`erabotics-theme`) and the cart's product list (`erabotics-cart`: product IDs, names, SKUs, prices). Cart data is validated on read and re-priced from the catalog at checkout, so tampering cannot lower a price. |
| URL parameters | Only Store search/filter/sort terms and a product ID — never personal data. |
| Forms | Honeypot field (`_gotcha`) against simple spam bots; phone/length validation on checkout. |

## Configured on the hosting provider (Vercel) — not in the HTML

These are real HTTP response headers set in `vercel.json` and applied by Vercel. They are **not** duplicated as `<meta http-equiv>` tags, because meta tags do not provide the same protection (and several of these headers cannot be set that way at all).

- `Content-Security-Policy` — only the site's own scripts (plus the hash of the small inline theme script), styles, fonts and images; network requests only to Formspree and Google Apps Script; form posts only to Formspree; no framing; no plugins. Google Forms, WhatsApp, Facebook and Instagram are ordinary links and are unaffected.
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
- **Formspree:** restrict submissions to `eraboticseg.com` and enable its spam protection (reCAPTCHA) in the form settings.
- **Google Apps Script (contact sheet):** the web-app URL is public by design, so validate and length-limit incoming fields inside the script, and keep the sheet's sharing limited to staff.
- **HSTS preload:** once every `*.eraboticseg.com` subdomain is confirmed to be HTTPS-only, the header can be extended with `includeSubDomains; preload` and submitted to hstspreload.org.

## If a backend is added later

None of the following exist today, because the site has no server, database or login. They would become required if a backend is introduced:

- Server-side validation and sanitisation of every input (never trust the browser), including server-side price calculation for orders and payments.
- Authentication and session security (secure, `HttpOnly`, `SameSite` cookies; password hashing; rate limiting; account lockout) and CSRF protection for state-changing requests.
- Parameterised queries / an ORM to prevent SQL or NoSQL injection; least-privilege database accounts; encrypted backups.
- Secrets kept in server-side environment variables (e.g. Vercel environment variables), never in frontend files.
- A privacy policy covering what personal data is collected, why, where it is stored and for how long — especially because the site serves parents and children.
- Logging and monitoring, dependency vulnerability scanning, and a process for applying security updates.
- For online payments: use the payment provider's hosted checkout so card data never touches ERABOTICS servers (PCI-DSS scope).
