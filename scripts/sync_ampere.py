"""Sync the ERABOTICS Store catalog from our supplier, Ampere Electronics.

Pulls every product from Ampere's public WooCommerce Store API, applies the
ERABOTICS markup, and writes the static catalog the Store page reads:

    assets/data/catalog.json          one compact entry per product
    assets/data/details/<n>.json      descriptions, split into small chunks

Usage (from the repository root):

    python scripts/sync_ampere.py            # default +20% markup
    python scripts/sync_ampere.py --markup 25

Then commit and push the updated assets/data folder to publish the new prices.
Standard library only — no packages to install.
"""
import argparse
import html
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

API = 'https://ampere-electronics.com/wp-json/wc/store/v1/products'
PER_PAGE = 100
CHUNK = 200  # products per details file
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'data')


def fetch(page, endpoint=''):
    url = f'{API}{endpoint}?per_page={PER_PAGE}&page={page}' + ('' if endpoint else '&orderby=id&order=asc')
    req = urllib.request.Request(url, headers={'User-Agent': 'ERABOTICS-catalog-sync/1.0', 'Accept': 'application/json'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                total_pages = int(r.headers.get('X-WP-TotalPages', '1'))
                return json.load(r), total_pages
        except Exception as e:  # network hiccup — back off and retry
            if attempt == 3:
                raise
            print(f'  page {page}: {e} — retrying', file=sys.stderr)
            time.sleep(3 * (attempt + 1))


class TextExtractor(HTMLParser):
    """Turns product HTML into plain text blocks (paragraphs and list items)."""
    BLOCK = {'p', 'div', 'li', 'br', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'table'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.buf, self.skip = [], [], 0

    def flush(self):
        text = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
        if text:
            self.blocks.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag in self.BLOCK:
            self.flush()

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def to_text(markup):
    if not markup:
        return []
    p = TextExtractor()
    p.feed(markup)
    p.flush()
    return p.blocks


def money(minor, unit):
    return int(minor) / (10 ** unit)


def marked_up(value, markup):
    # Round up to the next whole pound so the markup is never under 20%
    return int(math.ceil(round(value * (1 + markup / 100), 4)))


def image(p, size):
    imgs = p.get('images') or []
    if not imgs:
        return None
    img = imgs[0]
    if size == 'full':
        return img.get('src')
    m = re.search(r'(\S+)\s+300w', img.get('srcset') or '')
    return m.group(1) if m else img.get('thumbnail') or img.get('src')


def stock_qty(p):
    m = re.search(r'(\d+)\s+in stock', html.unescape((p.get('stock_availability') or {}).get('text') or ''))
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--markup', type=float, default=20.0, help='percentage added to the supplier price (default 20)')
    args = ap.parse_args()

    cats_raw, page, total = [], 1, 1
    while page <= total:
        items, total = fetch(page, '/categories')
        cats_raw.extend(items)
        page += 1
    by_id = {c['id']: c for c in cats_raw}

    def top_of(cid):
        c = by_id.get(cid)
        while c and c.get('parent') and c['parent'] in by_id:
            c = by_id[c['parent']]
        return c

    raw, page, total = [], 1, 1
    while page <= total:
        items, total = fetch(page)
        raw.extend(items)
        print(f'page {page}/{total}: {len(raw)} products', end='\r')
        page += 1
        time.sleep(0.4)  # be gentle with the supplier's server
    print()

    catalog, details, groups = [], {}, {}
    for p in raw:
        prices = p.get('prices') or {}
        unit = int(prices.get('currency_minor_unit') or 2)
        rng = prices.get('price_range')
        base = money(rng['min_amount'], unit) if rng else money(prices.get('price') or 0, unit)
        if base <= 0:
            continue  # price on request — nothing to sell online
        cats, tops = [], []
        for c in p.get('categories') or []:
            if (c.get('name') or '').lower() == 'uncategorized':
                continue
            name = html.unescape(c['name'])
            top = top_of(c['id'])
            top_name = html.unescape(top['name']) if top else name
            if top_name not in tops:
                tops.append(top_name)
            if name != top_name and name not in cats:
                cats.append(name)
        for t in tops:
            g = groups.setdefault(t, {'n': 0, 'sub': {}})
            g['n'] += 1
        for c in cats:
            for t in tops:
                sub = groups[t]['sub']
                sub[c] = sub.get(c, 0) + 1
        entry = {
            'id': p['id'],
            'n': html.unescape(p.get('name') or '').strip(),
            's': p.get('sku') or '',
            'g': tops,
            'c': cats,
            'p': marked_up(base, args.markup),
            'img': image(p, 'thumb'),
            'in': bool(p.get('is_in_stock')),
        }
        if rng:
            entry['from'] = True
        qty = stock_qty(p)
        if qty is not None:
            entry['q'] = qty
        catalog.append(entry)

        desc = to_text(p.get('short_description')) + to_text(p.get('description'))
        details[p['id']] = {'img': image(p, 'full'), 'd': desc[:60]}

    catalog.sort(key=lambda e: e['id'], reverse=True)  # newest first

    os.makedirs(os.path.join(OUT, 'details'), exist_ok=True)
    for f in os.listdir(os.path.join(OUT, 'details')):
        os.remove(os.path.join(OUT, 'details', f))
    for e in catalog:
        e['k'] = e['id'] // CHUNK  # which details chunk holds this product
    chunks = {}
    for e in catalog:
        chunks.setdefault(e['k'], {})[e['id']] = details[e['id']]
    for k, v in chunks.items():
        with open(os.path.join(OUT, 'details', f'{k}.json'), 'w', encoding='utf-8') as fh:
            json.dump(v, fh, ensure_ascii=False, separators=(',', ':'))

    meta = {
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'markup': args.markup,
        'currency': 'EGP',
        'groups': [
            {'name': g, 'count': v['n'], 'sub': sorted(v['sub'].items(), key=lambda kv: (-kv[1], kv[0]))}
            for g, v in sorted(groups.items(), key=lambda kv: (-kv[1]['n'], kv[0]))
        ],
        'products': catalog,
    }
    with open(os.path.join(OUT, 'catalog.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(os.path.join(OUT, 'catalog.json')) / 1024
    print(f'Wrote {len(catalog)} products ({size:.0f} KB), {len(groups)} category groups, {len(chunks)} detail chunks, markup +{args.markup:g}%')


if __name__ == '__main__':
    main()
