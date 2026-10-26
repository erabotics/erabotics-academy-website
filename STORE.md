# ERABOTICS Store — catalog, photos & orders

## Update prices and products

One-time setup on the computer that runs the sync: create `scripts/supplier.local.json` (it is git-ignored, so it never reaches GitHub or the website):

```json
{"api": "https://<supplier-domain>/wp-json/wc/store/v1"}
```

Then, from the repository root:

```bash
python scripts/sync_catalog.py            # +20% markup (default)
python scripts/sync_catalog.py --markup 25
```

This rewrites `assets/data/catalog.json` and `assets/data/details/`. Commit and push them to publish. Prices are a snapshot from the moment you run the script, so run it regularly (e.g. weekly). Carts re-check prices against the latest catalog at checkout.

## Product photos

Every product shows an ERABOTICS illustration for its category (`assets/img/parts/`). To use a real photo instead:

1. Photograph the product on a plain white background, square crop, about 800×800 px.
2. Save it in `assets/img/products/` named after the product's SKU — e.g. `7138.webp` (or `.jpg` / `.png`). The SKU is shown on each product card.
3. Run `python scripts/sync_catalog.py --photos-only`, then commit and push.

Products with real photos are listed first in the Store's "Featured" order. Only use photos you took yourself or have written permission to use.

## Orders

Checkout sends only product IDs and quantities to `POST /api/order`. The server looks up the real prices from `assets/data/catalog.json`, validates the customer details, saves the order in the database and (if `FORMSPREE_ENDPOINT` is set) emails the team. Staff see and update orders at **/admin** (sign-in required — see `SECURITY.md`). No payment is taken online: the team calls to confirm stock, delivery and the total, then collects cash on delivery or an InstaPay transfer.

Because prices are checked on the server, an order total can no longer be tampered with in the browser.

## Security

`vercel.json` sets a strict Content Security Policy and related headers. If you add a new third-party service (analytics, chat, payment provider), add its domain to the matching CSP directive or the browser will block it. If you edit the small inline theme script in each page's `<head>`, update its `sha256-` hash in the CSP too.
