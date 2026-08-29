"""Servidor de la carcasa web: pantalla por MJPEG y botones por POST.

Sin websockets ni X11: la pantalla del SeedSigner ya es un PIL.Image, asi que se sirve
como multipart/x-mixed-replace y el navegador la muestra con un <img>.
"""
import io
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ssemu import camera, dump, fake_gpio
from ssemu.display import framebuffer

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
BOUNDARY = "ssemuframe"

_pins = {}


def _load_pins():
    from seedsigner.hardware.buttons import HardwareButtonsConstants as K

    return {
        "KEY_UP": K.KEY_UP,
        "KEY_DOWN": K.KEY_DOWN,
        "KEY_LEFT": K.KEY_LEFT,
        "KEY_RIGHT": K.KEY_RIGHT,
        "KEY_PRESS": K.KEY_PRESS,
        "KEY1": K.KEY1,
        "KEY2": K.KEY2,
        "KEY3": K.KEY3,
    }


def _jpeg(image, quality=80):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.debug("ssemu-web: " + fmt, *args)

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
        elif path == "/stream":
            self._stream()
        elif path == "/frame.jpg":
            # Long-poll de un frame suelto: la pagina lo usa en vez de /stream porque una
            # conexion infinita se atasca en cualquier reverse proxy que haya en el medio
            # (y deja los clicks encolados detras). Vuelve apenas cambia la pantalla.
            query = parse_qs(urlparse(self.path).query)
            try:
                last_seq = int((query.get("seq") or ["-1"])[0])
            except ValueError:
                last_seq = -1
            seq, image = framebuffer.wait_for_next(last_seq, timeout=1.5)
            self._send(_jpeg(image, quality=90), "image/jpeg", headers=[("X-Frame-Seq", str(seq))])
        elif path == "/frame.png":
            _, image = framebuffer.current()
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
            # tap = click; down/up = el usuario mantiene apretado, y la repeticion
            # continua la hace el firmware con sus propios tiempos.
            action = (form.get("action") or ["tap"])[0]
            if key not in _pins or action not in ("tap", "down", "up"):
                self._send(b'{"error":"tecla o accion desconocida"}', "application/json", status=400)
                return
            {"tap": fake_gpio.tap, "down": fake_gpio.hold, "up": fake_gpio.release}[action](_pins[key])
            self._send(b'{"ok":true}', "application/json")
        elif path == "/api/camera":
            camera.source.select((form.get("file") or [""])[0])
            self._send(json.dumps(self._state()).encode(), "application/json")
        else:
            self._send(b"not found", "text/plain", status=404)

    def _state(self):
        resolved = camera.source.resolve()
        return {
            "files": [p.name for p in camera.source.list_files()],
            "selected": camera.source.selected or "",
            "resolved": resolved.name if resolved else None,
            "last_signed": dump.last_signed,
        }

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        last_seq = -1
        try:
            while True:
                last_seq, image = framebuffer.wait_for_next(last_seq)
                payload = _jpeg(image)
                self.wfile.write(
                    f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(payload)}\r\n\r\n".encode()
                )
                self.wfile.write(payload)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass


def start(port: int):
    global _pins
    _pins = _load_pins()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"ssemu: interfaz web escuchando en :{port}")
    return server
