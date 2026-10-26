"""Server-side product lookup: order prices always come from the catalog,
never from the browser."""
import json

from . import config

_cache = None


def products():
    global _cache
    if _cache is None:
        with open(config.CATALOG_PATH, encoding='utf-8') as fh:
            _cache = {p['id']: p for p in json.load(fh)['products']}
    return _cache
