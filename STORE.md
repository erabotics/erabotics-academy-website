# ERABOTICS Store — catalog & orders

The Store page lists our supplier's (Ampere Electronics) catalog with the ERABOTICS markup applied.

## Update prices and products

```bash
python scripts/sync_ampere.py            # +20% markup (default)
python scripts/sync_ampere.py --markup 25
```

This rewrites `assets/data/catalog.json` and `assets/data/details/`. Commit and push them — Vercel publishes the new prices automatically. Prices are a snapshot from the moment you run the script, so run it regularly (e.g. weekly). Carts re-check prices against the latest catalog at checkout.

## Orders

Checkout sends each order (reference number, items with SKUs, total, customer details) by email through the same Formspree form as the contact page. No payment is taken online: the team calls to confirm stock, delivery and the total, then collects cash on delivery or an InstaPay transfer.

Always check the SKUs and prices in an order email against the catalog before confirming — the order is assembled in the customer's browser.

## Security

`vercel.json` sets a strict Content Security Policy and related headers. If you add a new third-party service (analytics, chat, payment provider), add its domain to the matching CSP directive or the browser will block it. If you edit the small inline theme script in each page's `<head>`, update its `sha256-` hash in the CSP too.
