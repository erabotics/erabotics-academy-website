"""POST /api/order — place a store order (prices are checked on the server)."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # api/ (for the private _lib package)

from _lib import endpoints  # noqa: E402
from _lib.web import method_not_allowed, run  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        run(self, lambda: endpoints.submit_order(self))

    def do_GET(self):
        method_not_allowed(self, 'POST')

    def do_PUT(self):
        method_not_allowed(self, 'POST')

    def do_PATCH(self):
        method_not_allowed(self, 'POST')

    def do_DELETE(self):
        method_not_allowed(self, 'POST')
