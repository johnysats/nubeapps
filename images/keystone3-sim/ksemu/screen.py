"""Pantalla: captura la ventana SDL del simulador y la publica para el long-poll.

El firmware es un binario nativo que dibuja con SDL: no hay un PIL.Image al que engancharse
desde adentro como en krux o seedsigner. Corre contra un Xvfb y la pantalla se saca del
framebuffer X, como en ccq1 y kern -- pero sin VNC, porque una conexion infinita se atasca en
los reverse proxies y deja los clicks encolados detras.
"""
import os
import re
import subprocess
import threading
import time

from PIL import ImageGrab

# Techo de refresco. LVGL redibuja aunque no cambie nada; la comparacion contra el frame
# anterior evita publicar (y comprimir) lo que el usuario no va a ver.
MAX_FPS = 12

DISPLAY = os.environ.get("KSEMU_DISPLAY", ":99")
# El nombre se lo pone el driver SDL de LVGL (ui_simulator/lv_drivers/sdl/sdl.c).
WINDOW_NAME = "TFT Simulator"


class FrameBuffer:
    """Ultimo frame + numero de secuencia, para el long-poll de /frame.jpg."""

    def __init__(self, image):
        self._cond = threading.Condition()
        self._image = image
        self._seq = 0

    def put(self, image):
        with self._cond:
            self._image = image
            self._seq += 1
            self._cond.notify_all()

    def current(self):
        with self._cond:
            return self._seq, self._image

    def wait_for_next(self, last_seq, timeout=5.0):
        """Devuelve (seq, image); si no hubo cambios en `timeout` repite el actual."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self._image


framebuffer = None
geometry = (0, 0, 0, 0)  # x, y, ancho, alto de la ventana dentro del framebuffer X


def wait_for_window(timeout=60.0):
    """Geometria de la ventana SDL. Sin window manager, SDL la ubica donde quiere."""
    global geometry
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            info = subprocess.run(
                ["xwininfo", "-display", DISPLAY, "-name", WINDOW_NAME],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            info = ""
        match = re.search(
            r"Absolute upper-left X:\s+(-?\d+).*?"
            r"Absolute upper-left Y:\s+(-?\d+).*?"
            r"Width:\s+(\d+).*?Height:\s+(\d+)",
            info,
            re.S,
        )
        if match:
            geometry = tuple(int(value) for value in match.groups())
            return geometry
        time.sleep(0.3)
    raise RuntimeError(f"ksemu: la ventana '{WINDOW_NAME}' no aparecio en {timeout:.0f}s")


def grab():
    x, y, width, height = geometry
    return ImageGrab.grab(bbox=(x, y, x + width, y + height), xdisplay=DISPLAY)


def start():
    global framebuffer
    framebuffer = FrameBuffer(grab())
    return framebuffer


def run():
    """Bucle principal: framebuffer X -> frame publicado."""
    previous = None
    while True:
        started = time.monotonic()
        try:
            image = grab()
            # Comparar los bytes es mas barato que codificar un JPEG que nadie pidio.
            raw = image.tobytes()
            if raw != previous:
                previous = raw
                framebuffer.put(image)
        except OSError as error:  # el servidor X se cae o el simulador se esta reiniciando
            print("ksemu: no pude capturar la pantalla:", error)
            time.sleep(1)
        sleep = 1 / MAX_FPS - (time.monotonic() - started)
        if sleep > 0:
            time.sleep(sleep)
