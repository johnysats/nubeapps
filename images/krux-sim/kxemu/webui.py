"""Carcasa web: la pantalla por long-poll y los controles por POST.

Sin X11 ni VNC. El frame ya esta compuesto en memoria (pantalla + carcasa del dispositivo)
y se sirve como JPEG suelto: una conexion infinita tipo MJPEG se atasca en los reverse
proxies que haya en el medio y deja los clicks encolados detras.
"""
import io
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kxemu import camera, screen
from kxemu.remote import KEYS, remote

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.debug("kxemu-web: " + fmt, *args)

    def handle_one_request(self):
        # La pagina abandona el long-poll de /frame.jpg cada vez que se recarga o se cambia
        # de pestana; sin esto cada abandono deja un traceback de BrokenPipeError en el log.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, body: bytes, content_type: str, status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send((STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/frame.jpg":
            query = parse_qs(urlparse(self.path).query)
            last_seq = int((query.get("seq") or ["-1"])[0])
            seq, image = screen.framebuffer.wait_for_next(last_seq, timeout=1.5)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=90)
            self._send(buffer.getvalue(), "image/jpeg", headers=[("X-Frame-Seq", str(seq))])
        elif path == "/frame.png":
            _, image = screen.framebuffer.current()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            self._send(buffer.getvalue(), "image/png")
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
            if key not in KEYS:
                self._send(b'{"error":"tecla desconocida"}', "application/json", status=400)
                return
            remote.press(key)
            self._send(b'{"ok":true}', "application/json")
        elif path == "/api/touch":
            action = (form.get("action") or ["down"])[0]
            if action not in ("down", "move", "up"):
                self._send(b'{"error":"accion desconocida"}', "application/json", status=400)
                return
            # La pagina manda la posicion relativa a la imagen (0..1): el tamano en pantalla
            # depende del zoom que haya elegido el usuario.
            width, height = screen.window_size
            pos = (
                int(float((form.get("x") or ["0"])[0]) * width),
                int(float((form.get("y") or ["0"])[0]) * height),
            )
            remote.touch(pos, action)
            self._send(b'{"ok":true}', "application/json")
        elif path == "/api/camera":
            camera.source.select((form.get("file") or [""])[0])
            self._send(json.dumps(self._state()).encode(), "application/json")
        elif path == "/api/power":
            # Volver de un Shutdown: el proceso se rearranca, como enchufar el dispositivo.
            remote.power_on()
            self._send(b'{"ok":true}', "application/json")
        else:
            self._send(b"not found", "text/plain", status=404)

    def _state(self):
        resolved = camera.source.resolve()
        return {
            "files": camera.source.list_files(),
            "selected": camera.source.selected or "",
            "resolved": os.path.basename(resolved) if resolved else None,
            "powered_off": remote.powering_off,
        }


_server = None


def start(port: int):
    global _server
    _server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    _server.daemon_threads = True
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    logger.info("kxemu: interfaz web escuchando en :%s", port)
    return _server


def stop():
    """Libera el puerto antes de rearrancar el proceso."""
    if _server is not None:
        _server.shutdown()
        _server.server_close()
