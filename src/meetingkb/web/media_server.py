"""Tiny local static file server for the KB player.

Serves meeting videos, generated thumbnail sprites, and the Plyr player page to
an <iframe>. Streamlit's own media server hashes URLs and cannot serve the extra
thumbnail/VTT assets a real player needs, so we run a small, Range-capable
static server on 127.0.0.1 instead. Range support is required for video seeking.
"""
from __future__ import annotations

import http.server
import os
import threading
from functools import partial
from pathlib import Path

_EXT = {
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".vtt": "text/vtt",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".js": "text/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
}


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the Streamlit console quiet
        pass

    def guess_type(self, path):
        ext = os.path.splitext(str(path))[1].lower()
        return _EXT.get(ext) or super().guess_type(path)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.end_headers()

    def _resolve(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404, "Not found")
            return None
        return path

    def do_HEAD(self) -> None:
        path = self._resolve()
        if not path:
            return
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.end_headers()

    def do_GET(self) -> None:
        path = self._resolve()
        if not path:
            return
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end, is_partial = 0, size - 1, False
        if rng and rng.startswith("bytes="):
            spec = rng[len("bytes="):].split(",")[0].strip()
            s, _, e = spec.partition("-")
            try:
                if s == "":
                    start, end = max(0, size - int(e)), size - 1
                else:
                    start, end = int(s), (int(e) if e else size - 1)
                end = min(end, size - 1)
                if start > end or start >= size:
                    raise ValueError
                is_partial = True
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(206 if is_partial else 200)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        if is_partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)


_started: dict[str, str] = {}
_lock = threading.Lock()


def start_media_server(root: Path, preferred_port: int = 8600) -> str:
    """Start (once per process, per root) a background static server; return its base URL."""
    key = str(Path(root).resolve())
    with _lock:
        if key in _started:
            return _started[key]
        handler = partial(_Handler, directory=key)
        httpd = None
        for port in range(preferred_port, preferred_port + 25):
            try:
                httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
                break
            except OSError:
                continue
        if httpd is None:
            raise RuntimeError("No free port for the media server")
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        _started[key] = base
        return base
