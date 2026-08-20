"""Control remoto del simulador: teclas y toques que llegan por HTTP.

Upstream ya tiene el enganche: los mocks de `buttons` y `sensor` aceptan un
"sequence executor" (lo que usa el CI para las capturas de la documentacion) y le leen
`.key` y `.camera_image`. Registramos este objeto en su lugar y el firmware queda intacto.

A proposito NO se registra en `pmu`: el boton de encendido tambien consume `key == K_UP`,
asi que compartirlo con PAGE_PREV apagaria el dispositivo cada dos por tres.
"""
import threading
import time

import pygame as pg

from kxemu import camera

# Si el firmware nunca lee la tecla (esa pantalla no escucha ese boton), se descarta en vez
# de quedar pendiente y dispararse sola en la pantalla siguiente.
KEY_TIMEOUT = 2.0
TOUCH_TIMEOUT = 2.0

KEYS = {
    "ENTER": pg.K_RETURN,
    "PAGE": pg.K_DOWN,
    "PAGE_PREV": pg.K_UP,
}


class Remote:
    """Estado compartido entre el servidor web y los mocks del hardware."""

    def __init__(self):
        self.key = None
        self._key_at = 0.0
        self._point = None  # coordenadas dentro de la ventana, no del LCD
        self._point_at = 0.0
        self._point_read = False
        self._point_released = False
        # Apagado vs reinicio: los dos terminan en machine.reset(), que en el simulador
        # postea un QUIT. Lo unico que los distingue es que apagar duerme el PMU antes.
        self.powering_off = False
        self._power_on = threading.Event()

    # --- botones -------------------------------------------------------------
    def press(self, name):
        self.key = KEYS[name]
        self._key_at = time.monotonic()

    # --- pantalla tactil -----------------------------------------------------
    def touch(self, pos, action):
        if action == "up":
            self._point_released = True
            return
        self._point = pos
        self._point_at = time.monotonic()
        self._point_released = False
        if action == "down":
            self._point_read = False
            from krux.touchscreens.ft6x36 import touch_control

            # Guarda el irq_point leyendo current_point(): ya apunta a self._point.
            touch_control.trigger_event()

    def point(self):
        """Lo que ve el driver tactil: (x, y) mientras se mantiene, None al soltar."""
        if self._point is None:
            return None
        if time.monotonic() - self._point_at > TOUCH_TIMEOUT:
            self._point = None
            return None
        self._point_read = True
        if self._point_released:
            # Un click suelta enseguida: se entrega una vez mas para que el firmware
            # alcance a muestrearlo, y recien despues se reporta como soltado.
            pos, self._point = self._point, None
            return pos
        return self._point

    # --- camara --------------------------------------------------------------
    # El mock de `sensor` lee este atributo en cada snapshot y lo pone en None cuando
    # logro decodificar un QR: eso es lo que hace avanzar el QR animado.
    @property
    def camera_image(self):
        return camera.frame()

    @camera_image.setter
    def camera_image(self, value):
        if value is None:
            camera.consumed()

    # --- encendido -----------------------------------------------------------
    def power_on(self):
        """Vuelve a encender el dispositivo despues de un Shutdown."""
        self._power_on.set()

    def wait_power_on(self):
        self._power_on.wait()
        self._power_on.clear()
        self.powering_off = False

    # --- mantenimiento -------------------------------------------------------
    def tick(self):
        if self.key is not None and time.monotonic() - self._key_at > KEY_TIMEOUT:
            self.key = None


remote = Remote()


def install():
    """Registra el control remoto en los mocks y desvia el tactil hacia el."""
    from kruxsim.mocks import buttons, pmu, sensor
    from kruxsim.mocks.touchscreen_common import TCOMMON

    buttons.register_sequence_executor(remote)
    sensor.register_sequence_executor(remote)

    # PowerManager.shutdown() duerme el PMU antes de resetear; reboot() no. Es el unico
    # dato que deja para saber si el QUIT que viene despues es apagado o reinicio.
    def enter_sleep_mode(self):
        remote.powering_off = True

    pmu.PMUController.enter_sleep_mode = enter_sleep_mode

    # to_screen_pos() traduce de la ventana al LCD; lo unico que cambia es de donde sale
    # el punto: en vez del mouse de SDL, del ultimo POST /api/touch.
    def current_point(self):
        pos = remote.point()
        return self.to_screen_pos(pos) if pos else None

    TCOMMON.current_point = current_point
