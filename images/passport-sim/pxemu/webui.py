"""Carcasa web: la pantalla por long-poll y los controles por POST.

Como en las otras apps del store, la pantalla no va por una conexion infinita tipo MJPEG:
esa se atasca en los reverse proxies del medio y deja los clicks encolados detras.
"""
import io
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

device = None
camera_source = None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.debug("pxemu-web: " + fmt, *args)

    def handle_one_request(self):
        # La pagina abandona el long-poll cada vez que se recarga o se cambia de pestana.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, body, content_type, status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _image(self, image, seq, scale):
        # PNG y ampliado por un factor entero desde el servidor: la pantalla son 240x320 de
        # texto nitido y dejar que el navegador la estire se come filas de pixeles enteras.
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self._send(buffer.getvalue(), "image/png", headers=[("X-Frame-Seq", str(seq))])

    @staticmethod
    def _int(query, name, default, low, high):
        try:
            return max(low, min(high, int(query[name][0])))
        except (KeyError, ValueError):
            return default

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            self._send((STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/frame.png":
            if "seq" in query:
                seq, image = device.framebuffer.wait_for_next(
                    self._int(query, "seq", -1, -1, 2 ** 31), timeout=1.5)
            else:
                seq, image = device.framebuffer.current()
            self._image(image, seq, self._int(query, "scale", 1, 1, 4))
        elif path == "/api/state":
            self._send(json.dumps(self._state()).encode(), "application/json")
        else:
            self._send(b"not found", "text/plain", status=404)

    def do_HEAD(self):
        # Sin esto BaseHTTPRequestHandler responde 501 a cualquier healthcheck con HEAD.
        self._send(b"", "text/html; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        form = parse_qs(self.rfile.read(length).decode())

        if path == "/api/button":
            key = (form.get("key") or [""])[0]
            action = (form.get("action") or ["tap"])[0]
            if not device.press(key, action):
                self._send(b'{"error":"tecla desconocida"}', "application/json", status=400)
                return
            self._send(b'{"ok":true}', "application/json")
        elif path == "/api/camera":
            camera_source.select((form.get("file") or [""])[0])
            self._send(json.dumps(self._state()).encode(), "application/json")
        else:
            self._send(b"not found", "text/plain", status=404)

    def _state(self):
        resolved = camera_source.resolve()
        return {
            "files": camera_source.list_files(),
            "selected": camera_source.selected or "",
            "resolved": os.path.basename(resolved) if resolved else None,
            "camera_on": device.camera_on,
            "genuine": device.genuine_led,
        }


def start(port, dev, source):
    global device, camera_source
    device, camera_source = dev, source
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("pxemu: interfaz web escuchando en :%s", port)
    return server
