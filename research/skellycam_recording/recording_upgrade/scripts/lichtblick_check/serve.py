"""Static server on localhost with HTTP Range: the Lichtblick web build at / and the take at /data/.

  python -I serve.py <app_dir> <data_dir> <port>

Sends the COOP/COEP headers Lichtblick's vercel.json sets. Logs Range requests to stderr.
"""
import http.server, os, sys
from functools import partial

APP, DATA, PORT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3])
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm", ".mcap": "application/octet-stream",
         ".html": "text/html", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml",
         ".ttf": "font/ttf", ".woff2": "font/woff2", ".ico": "image/x-icon", ".map": "application/json"}


class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        root, rel = (DATA, path[len("/data/"):]) if path.startswith("/data/") else (APP, path.lstrip("/"))
        full = os.path.abspath(os.path.join(root, *[p for p in rel.split("/") if p not in ("", ".", "..")]))
        if not full.startswith(root):  # never serve outside the two roots
            return os.path.join(root, "__nope__")
        return full

    def guess_type(self, path):
        return TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        a, b = rng.removeprefix("bytes=").split(",")[0].split("-")
        start, end = (size - int(b), size - 1) if a == "" else (int(a), min(int(b) if b else size - 1, size - 1))
        if start >= size or start > end:
            self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            self.wfile.write(f.read(end - start + 1))

    def log_message(self, fmt, *args):
        if "/data/" in self.path:
            sys.stderr.write(f"{self.command} {self.path} {self.headers.get('Range')}\n")


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
