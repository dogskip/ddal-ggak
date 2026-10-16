import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pricing import total


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        value = f"{total(2, discounted=self.path == '/'):.2f}"
        body = Path("page.html").read_text().replace("{{value}}", value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
