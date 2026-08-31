"""Control remoto: los toques que llegan por HTTP entran como mouse en el Xvfb.

El simulador de upstream registra `lv_sdl_mouse` como dispositivo de entrada, asi que para
LVGL el mouse *es* la pantalla tactil del dispositivo. No hace falta ningun mock: alcanza con
mover el puntero y apretar el boton dentro de la ventana.
"""
import os
import subprocess

from kxsim import screen

DISPLAY = os.environ.get("KXSIM_DISPLAY", ":99")


def _xdotool(*args):
    try:
        subprocess.run(
            ["xdotool", *args],
            env={**os.environ, "DISPLAY": DISPLAY},
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print("kxsim: xdotool fallo:", error)


def touch(relative_x, relative_y, action):
    """La pagina manda la posicion relativa (0..1): el tamano en pantalla depende del zoom.

    `down`/`move`/`up` por separado, no un tap: asi un arrastre en la pagina es un arrastre
    en el dispositivo (el firmware navega con swipes las vistas de QR con zoom) y mantener
    apretado se comporta como mantener apretado.
    """
    x, y, width, height = screen.geometry
    # El puntero se mueve en coordenadas del framebuffer X, no de la ventana.
    position = (
        str(x + min(max(int(relative_x * width), 0), width - 1)),
        str(y + min(max(int(relative_y * height), 0), height - 1)),
    )
    if action == "down":
        _xdotool("mousemove", *position, "mousedown", "1")
    elif action == "move":
        _xdotool("mousemove", *position)
    elif action == "up":
        _xdotool("mousemove", *position, "mouseup", "1")
