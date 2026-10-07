"""Sync the ERABOTICS Store catalog.

Pulls every product from the supplier's WooCommerce Store API, applies the
ERABOTICS markup, assigns each product an image, and writes the static
catalog the Store page reads:

    assets/data/catalog.json          one compact entry per product
    assets/data/details/<n>.json      descriptions, split into small chunks

Images: a product uses our own photo when one exists in
assets/img/products/ named after its SKU (e.g. 7138.webp / 7138.jpg / 7138.png);
otherwise it gets the ERABOTICS illustration for its category
(assets/img/parts/<kind>.svg). Supplier photos are never used.

The supplier API address is kept out of the repository. Set it once in
scripts/supplier.local.json (git-ignored):

    {"api": "https://<supplier-domain>/wp-json/wc/store/v1"}

or in the CATALOG_SOURCE_API environment variable.

Usage (from the repository root):

    python scripts/sync_catalog.py                 # fetch + default +20% markup
    python scripts/sync_catalog.py --markup 25
    python scripts/sync_catalog.py --photos-only   # just pick up new photos, no fetch

Then commit and push assets/data (and any new photos) to publish.
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

PER_PAGE = 100
CHUNK = 200  # products per details file
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'data')
PHOTOS = os.path.join(ROOT, 'assets', 'img', 'products')
PHOTO_EXT = ('.webp', '.jpg', '.jpeg', '.png')
URLISH = re.compile(r'(https?://|www\.|\.com\b|\.net\b|@\w+\.\w)', re.I)

# Category illustration rules: first match wins (matched against name + categories)
KINDS = [
    ('ic', r'\b74(hc|hct|ls|xx)?\d{2,3}\b|\bics?\b'),
    ('module', r'usb to|\bttl\b|rs-?232|rs-?485|can bus'),
    ('capacitor', r'capacitor'),
    ('resistor', r'resistor|potentiometer|trimmer|rheostat|varistor'),
    ('battery', r'batter|18650|li-?ion|lipo|cell holder'),
    ('fan', r'\bfans?\b|heat ?sink'),
    ('board', r'arduino|raspberry|esp32|esp8266|esp-|development board|dev board|nodemcu|stm32|\bshields?\b'),
    ('display', r'\blcd|\boled|\btft|7-seg|display'),
    ('led', r'\bleds?\b'),
    ('motor', r'motor|servo|stepper'),
    ('sensor', r'sensor|ultrasonic|detector|\bpir\b|thermistor|load cell'),
    ('power', r'power supply|converter|charger|solar|inverter|adapter|transformer|\bbuck\b|\bboost\b|\bsmps\b'),
    ('printing', r'filament|nozzle|extruder|3d print|hot ?end|\bpla\b|\bpetg\b|\babs\b|\btpu\b|\besun\b'),
    ('mechanical', r'bearing|linear rail|\brail\b|shaft|coupling|pulley|\bbelt|gear|aluminum profile|lead ?screw|\bcnc\b|cable chain|end mill|engraving|drill bit|collet|chuck|spindle|carriage|lead nut'),
    ('hardware', r'screw|\bnuts?\b|washer|spacer|standoff|magnet|\bbolt'),
    ('wire', r'\bwires?\b|cable|crocodile|heat ?shrink|sleev|jumper|wrapping'),
    ('connector', r'connector|header|terminal|socket|\bplug|\bjack\b|dupont|\bjst\b|d-sub|banana'),
    ('pcb', r'breadboard|\bpcbs?\b|perf ?board|prototype board|strip ?board'),
    ('box', r'\bbox(es)?\b|enclosure'),
    ('tool', r'solder|\btools?\b|tweezer|plier|cutter|screwdriver|\bglue|\btape\b|flux|desolder|\biron\b|knife|wrench|stripper'),
    ('meter', r'multimeter|voltmeter|ammeter|wattmeter|panel meter|measuring|oscilloscope|\btester\b|\blcr\b|clamp meter'),
    ('switch', r'breaker|switch|push ?button|\bbuttons?\b|keypad|joystick'),
    ('module', r'module|driver|relay|\bboard\b'),
    ('ic', r'\bics?\b|74xx|74hc|transistor|mosfet|diode|regulator|rectifier|crystal|oscillator|microcontroller|\bsmd\b|optocoupler|triac|thyristor|\bfuses?\b|inductor|\bcoil|buzzer|component'),
]
KINDS = [(k, re.compile(rx, re.I)) for k, rx in KINDS]


def kind_for(*texts):
    # The product name is the strongest signal, then its subcategories, then its group
    for text in texts:
        for k, rx in KINDS:
            if text and rx.search(text):
                return k
    return 'part'


def own_photo(sku):
    if not sku:
        return None
    for ext in PHOTO_EXT:
        name = f'{sku}{ext}'
        if os.path.exists(os.path.join(PHOTOS, name)):
            return f'assets/img/products/{name}'
    return None


def source_api():
    api = os.environ.get('CATALOG_SOURCE_API')
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'supplier.local.json')
    if not api and os.path.exists(cfg):
        api = json.load(open(cfg, encoding='utf-8')).get('api')
    if not api:
        sys.exit('Set the supplier API in scripts/supplier.local.json or CATALOG_SOURCE_API (see the top of this file).')
    return api.rstrip('/') + '/products'


def fetch(api, page, endpoint=''):
    url = f'{api}{endpoint}?per_page={PER_PAGE}&page={page}' + ('' if endpoint else '&orderby=id&order=asc')
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
        if text and not URLISH.search(text):  # drop lines carrying links or other shops' addresses
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
    # Round up to the next whole pound so the markup is never under the target
    return int(math.ceil(round(value * (1 + markup / 100), 4)))


def stock_qty(p):
    m = re.search(r'(\d+)\s+in stock', html.unescape((p.get('stock_availability') or {}).get('text') or ''))
    return int(m.group(1)) if m else None


def assign_images(catalog):
    counts, photos = {}, 0
    for e in catalog:
        e['ic'] = kind_for(e['n'], ' '.join(e['c']), ' '.join(e['g']))
        counts[e['ic']] = counts.get(e['ic'], 0) + 1
        photo = own_photo(e['s'])
        if photo:
            e['img'] = photo
            photos += 1
        else:
            e.pop('img', None)
    return counts, photos


def write_catalog(meta):
    with open(os.path.join(OUT, 'catalog.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, separators=(',', ':'))
    return os.path.getsize(os.path.join(OUT, 'catalog.json')) / 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--markup', type=float, default=20.0, help='percentage added to the supplier price (default 20)')
    ap.add_argument('--photos-only', action='store_true', help='re-assign images from assets/img/products without fetching')
    args = ap.parse_args()

    if args.photos_only:
        meta = json.load(open(os.path.join(OUT, 'catalog.json'), encoding='utf-8'))
        counts, photos = assign_images(meta['products'])
        write_catalog(meta)
        print(f'{photos} products now use our own photos; the rest use illustrations.')
        return

    api = source_api()
    cats_raw, page, total = [], 1, 1
    while page <= total:
        items, total = fetch(api, page, '/categories')
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
        items, total = fetch(api, page)
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
            'in': bool(p.get('is_in_stock')),
        }
        if rng:
            entry['from'] = True
        qty = stock_qty(p)
        if qty is not None:
            entry['q'] = qty
        catalog.append(entry)

        desc = to_text(p.get('short_description')) + to_text(p.get('description'))
        details[p['id']] = {'d': desc[:60]}

    catalog.sort(key=lambda e: e['id'], reverse=True)  # newest first
    counts, photos = assign_images(catalog)

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
    size = write_catalog(meta)
    print(f'Wrote {len(catalog)} products ({size:.0f} KB), {len(groups)} category groups, {len(chunks)} detail chunks, markup +{args.markup:g}%')
    print(f'Images: {photos} own photos; illustrations by kind: ' + ', '.join(f'{k} {n}' for k, n in sorted(counts.items(), key=lambda kv: -kv[1])))


if __name__ == '__main__':
    main()
