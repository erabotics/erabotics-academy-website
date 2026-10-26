"""GET /api/admin/orders — list orders; PATCH — change an order's status."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # api/ (for the private _lib package)

from _lib import endpoints  # noqa: E402
from _lib.web import method_not_allowed, run  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        run(self, lambda: endpoints.admin_list(self, 'orders'))

    def do_PATCH(self):
        run(self, lambda: endpoints.admin_update_status(self, 'orders'))

    def do_POST(self):
        method_not_allowed(self, 'GET, PATCH')

    def do_PUT(self):
        method_not_allowed(self, 'GET, PATCH')

    def do_DELETE(self):
        method_not_allowed(self, 'GET, PATCH')
