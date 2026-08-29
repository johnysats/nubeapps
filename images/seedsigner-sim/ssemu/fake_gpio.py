"""Modulo RPi.GPIO falso: los 8 pines de los botones viven en memoria.

`hardware/buttons.py` de upstream queda intacto -- su debounce, sus thresholds de
225/250 ms y el disparo del screensaver siguen siendo los de SeedSigner. Lo unico que
cambia es de donde sale el nivel del pin: en vez de un GPIO real, de las pulsaciones
que manda la pagina web.

El pin no se baja por un tiempo fijo: se mantiene bajo hasta que el firmware lo lee.
Con un pulso fijo, cualquier click que caiga mientras el thread principal esta
renderizando (o sea, fuera del bucle de `wait_for`) se perdia entero.
"""
import threading
import time
from collections import deque


# Constantes que usa buttons.py (y nada mas).
BOARD = "BOARD"
BCM = "BCM"
IN = "IN"
OUT = "OUT"
HIGH = 1
LOW = 0
PUD_UP = "PUD_UP"
PUD_DOWN = "PUD_DOWN"
RPI_INFO = {"P1_REVISION": 3}  # 3 = GPIO de 40 pines, el layout que asume SeedSigner
VERSION = "0.0.0-ssemu"

PRESS_MIN_MS = 90       # cuanto sigue bajo el pin despues de que el firmware lo leyo
UNREAD_TIMEOUT_MS = 2000  # tecla que esta pantalla no escucha: se suelta igual
REPEAT_GAP_MS = 270     # buttons.py descarta la misma tecla dos veces dentro de 250 ms
MAX_HOLD_S = 5.0        # si nunca llega el "solte la tecla" (pestana cerrada, red cortada)

_lock = threading.Lock()
_state = {}
_pending = deque()
_active = None
_read_at = None
_release_requested = False
_last_release_pin = None
_last_release_read_at = 0.0
_worker = None


def setmode(mode):
    pass


def setwarnings(flag):
    pass


def setup(pin, mode, pull_up_down=None, initial=None):
    with _lock:
        _state[pin] = HIGH  # pull-up: en reposo el pin esta alto


def input(pin):
    """Lectura del pin. La primera lectura en bajo es la que "consume" la pulsacion."""
    global _read_at
    with _lock:
        value = _state.get(pin, HIGH)
        if value == LOW and pin == _active and _read_at is None:
            _read_at = time.monotonic()
        return value


def output(pin, value):
    with _lock:
        _state[pin] = value


def cleanup(pin=None):
    pass


def tap(pin):
    """Click: se mantiene bajo hasta que lo lean y despues se suelta solo."""
    _enqueue(pin, release_on_read=True)


def hold(pin):
    """El usuario mantiene apretado: el pin queda bajo hasta el release.

    Asi la repeticion continua la hace el propio firmware, con sus tiempos.
    """
    _enqueue(pin, release_on_read=False)


def release(pin):
    global _release_requested
    with _lock:
        if _active == pin:
            _release_requested = True
            return
        # Todavia esta en la cola: que se comporte como un click comun.
        for index, (queued_pin, _) in enumerate(_pending):
            if queued_pin == pin:
                _pending[index] = (pin, True)


def _enqueue(pin, release_on_read):
    global _worker
    with _lock:
        _pending.append((pin, release_on_read))
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, daemon=True)
            _worker.start()


def _run():
    global _active, _read_at, _release_requested, _last_release_pin, _last_release_read_at

    while True:
        with _lock:
            if not _pending:
                return
            pin, release_on_read = _pending.popleft()
            # Se marca activo antes de esperar el gap, no despues: durante esa espera el pin
            # no estaba ni en la cola ni en _active, asi que un release que cayera ahi no lo
            # encontraba y se perdia entero (la tecla quedaba apretada hasta MAX_HOLD_S).
            # El pin sigue en HIGH mientras tanto, asi que ninguna lectura cuenta todavia.
            _active = pin
            _read_at = None
            _release_requested = release_on_read

        _wait_repeat_gap(pin)

        with _lock:
            _state[pin] = LOW
        started = time.monotonic()

        while True:
            time.sleep(0.005)
            now = time.monotonic()
            with _lock:
                read_at = _read_at
                wants_release = _release_requested
            if wants_release and read_at and now - read_at >= PRESS_MIN_MS / 1000:
                break
            if wants_release and not read_at and now - started >= UNREAD_TIMEOUT_MS / 1000:
                break
            if now - started >= MAX_HOLD_S:
                break

        with _lock:
            _state[pin] = HIGH
            _active = None
            _last_release_pin = pin
            _last_release_read_at = _read_at or time.monotonic()


def _wait_repeat_gap(pin):
    """Dos clicks de la misma tecla muy juntos: buttons.py los toma como un hold."""
    with _lock:
        if pin != _last_release_pin:
            return
        elapsed = time.monotonic() - _last_release_read_at
    remaining = REPEAT_GAP_MS / 1000 - elapsed
    if remaining > 0:
        time.sleep(remaining)
