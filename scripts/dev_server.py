"""Local development server: serves the static site like Vercel (clean URLs,
vercel.json headers) and runs the Python functions in api/.

    python scripts/dev_server.py            # http://localhost:5173
    python scripts/dev_server.py 8080

Reads settings from .env (see .env.example). Not used in production.
"""
import importlib.util
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'api'))
import _lib.config  # noqa: E402,F401  (loads .env)

_modules = {}


def api_handler(path):
    """Load api/<path>.py and return its `handler` class, or None."""
    rel = path.strip('/').split('?')[0]
    if '..' in rel or any(part.startswith(('_', '.')) for part in rel.split('/')):
        return None  # private modules (api/_lib) are never endpoints
    file = os.path.join(ROOT, *rel.split('/')) + '.py'
    if not os.path.isfile(file):
        return None
    if file not in _modules:
        spec = importlib.util.spec_from_file_location(rel.replace('/', '_'), file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _modules[file] = mod.handler
    return _modules[file]


class DevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _api(self, method):
        cls = api_handler(self.path)
        if not cls or not hasattr(cls, f'do_{method}'):
            self.send_error(404)
            return
        getattr(cls, f'do_{method}')(self)  # run the Vercel handler method on this request

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._api('GET')
        return super().do_GET()

    def do_POST(self):
        self._api('POST')

    def do_PATCH(self):
        self._api('PATCH')

    def send_head(self):
        path = self.path.split('?')[0].split('#')[0]
        parts = [p for p in path.split('/') if p]
        # Same rule as production: secrets, source and tooling are never served
        if any(p.startswith('.') for p in parts) or (parts and parts[0] in ('api', 'scripts')) \
                or path.endswith(('.py', '.md', '.txt')):
            self.send_error(404)
            return None
        if path != '/' and not os.path.splitext(path)[1] and os.path.exists(os.path.join(ROOT, path.lstrip('/') + '.html')):
            self.path = path + '.html'
        return super().send_head()

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store')
            with open(os.path.join(ROOT, 'vercel.json'), encoding='utf-8') as fh:
                for rule in json.load(fh).get('headers', []):
                    if rule['source'] == '/(.*)':
                        for h in rule['headers']:
                            self.send_header(h['key'], h['value'])
        super().end_headers()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    print(f'ERABOTICS dev server on http://localhost:{port}')
    ThreadingHTTPServer(('127.0.0.1', port), DevHandler).serve_forever()
