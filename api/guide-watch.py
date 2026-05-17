from http.server import BaseHTTPRequestHandler

from _local_proxy import proxy_or_error


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return proxy_or_error(self, "/api/guide-watch", query)
