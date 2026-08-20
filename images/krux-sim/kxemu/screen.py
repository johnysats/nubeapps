"""Pantalla: bombea la cola de eventos de pygame y publica el frame compuesto.

Los mocks del LCD no dibujan: postean el dibujo como evento de pygame para que corra en el
hilo principal (el firmware corre en otro hilo). Este es el mismo bucle de
`simulator/simulator.py` de upstream, pero en vez de mostrar una ventana SDL guarda el
frame para que la pagina lo pida por HTTP.
"""
import os
import sys
import threading
import time

import pygame as pg
from PIL import Image

# Techo de refresco de la pagina. El firmware postea un evento por primitiva dibujada
# (cada string, cada rectangulo): publicar uno por uno seria un frame por letra.
MAX_FPS = 30


class FrameBuffer:
    """Ultimo frame + numero de secuencia, para el long-poll de /frame.jpg."""

    def __init__(self, size):
        self._cond = threading.Condition()
        self._image = Image.new("RGB", size, "black")
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
window_size = (0, 0)


def start(device):
    """Crea la superficie (sin ventana: SDL_VIDEODRIVER=dummy) y el framebuffer."""
    global framebuffer, window_size
    from kruxsim import devices

    window_size = devices.WINDOW_SIZES[device]
    screen = pg.display.set_mode(window_size, 0, 32)
    framebuffer = FrameBuffer(window_size)
    return screen


def run(screen, device, remote):
    """Bucle principal: eventos del firmware -> frame publicado."""
    from kruxsim import devices

    buffer_image = screen.copy().convert()
    device_image = devices.load_image(device)
    dirty = True
    last_publish = 0.0

    while True:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                # machine.reset(): el firmware se reinicia (cambiar el tema, restaurar
                # settings...) o se apaga. Upstream cierra la ventana y termina; aca eso
                # dejaba el contenedor muerto, asi que se rearranca el proceso entero.
                if remote.powering_off:
                    _publish(buffer_image, device_image, off=True)
                    remote.wait_power_on()
                _reboot()
            if event.type >= pg.USEREVENT and "f" in event.dict:
                event.dict["f"]()
                dirty = True

        remote.tick()

        now = time.monotonic()
        if dirty and now - last_publish >= 1 / MAX_FPS:
            _publish(buffer_image, device_image)
            dirty = False
            last_publish = now

        time.sleep(0.005)


def _publish(buffer_image, device_image, off=False):
    """Compone pantalla + carcasa y lo deja disponible para /frame.jpg."""
    from kruxsim.mocks import lcd

    if off:
        # Apagado: la carcasa sin nada encendido adentro.
        buffer_image.fill((0, 0, 0))
    elif lcd.screen:
        rect = lcd.screen.get_rect()
        rect.center = buffer_image.get_rect().center
        buffer_image.blit(lcd.screen, rect)
    if device_image:
        rect = device_image.get_rect()
        rect.center = buffer_image.get_rect().center
        buffer_image.blit(device_image, rect)
    framebuffer.put(Image.frombytes("RGB", window_size, pg.image.tobytes(buffer_image, "RGB")))


def _reboot():
    """Rearranca el proceso: es el equivalente al reset del K210."""
    from kxemu import webui

    webui.stop()
    pg.quit()
    os.execv(sys.executable, [sys.executable] + sys.argv)
