#!/usr/bin/env python3
"""Punto de entrada del contenedor: arranca el simulador de Kern headless.

Xvfb -> firmware (SDL) -> captura de la ventana -> HTTP. Los toques vuelven por el mismo
camino como eventos de mouse, que es lo que LVGL ya trata como pantalla tactil.
"""
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kxsim import camera, device, screen, webui

HELP_DIR = "/app/help"
DATA_DIR = os.environ.get("KXSIM_DATA_DIR", "/data")
SD_DIR = os.environ.get("KXSIM_SD_DIR", "/data/sdcard")
RUN_DIR = os.environ.get("KXSIM_RUN_DIR", "/run/kxsim")
DISPLAY = os.environ.get("KXSIM_DISPLAY", ":99")
PORT = int(os.environ.get("KXSIM_PORT", "6080"))
# El framebuffer tiene que ser mas grande que la ventana: sin window manager SDL la ubica
# donde quiere y una ventana pegada al borde saldria cortada.
SCREEN_SIZE = "800x800x24"


def seed_help():
    """LEEME + seed de ejemplo la primera vez: una MicroSD vacia no dice como se usa.

    Solo si no hay ningun archivo, asi que si el usuario ya guardo lo suyo (o borro el LEEME)
    no vuelve a aparecer.
    """
    try:
        os.makedirs(SD_DIR, exist_ok=True)
        if any(name for name in os.listdir(SD_DIR) if not name.startswith(".")):
            return
        for name in os.listdir(HELP_DIR):
            shutil.copyfile(os.path.join(HELP_DIR, name), os.path.join(SD_DIR, name))
    except OSError as error:
        print("kxsim: no pude dejar la ayuda en la MicroSD:", error)


def start_xvfb():
    # Un `docker restart` conserva el filesystem del contenedor pero no los procesos: el
    # lock del arranque anterior queda huerfano y Xvfb se niega a usar el display.
    try:
        os.remove(f"/tmp/.X{DISPLAY.lstrip(':')}-lock")
    except OSError:
        pass
    process = subprocess.Popen(
        ["Xvfb", DISPLAY, "-screen", "0", SCREEN_SIZE, "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Xvfb tarda un instante en aceptar conexiones; el firmware muere si SDL no encuentra
    # el display, asi que se espera a que exista antes de arrancarlo.
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("kxsim: Xvfb no arranco")
        if subprocess.run(
            ["xdpyinfo", "-display", DISPLAY], capture_output=True
        ).returncode == 0:
            return process
        time.sleep(0.1)
    raise RuntimeError(f"kxsim: Xvfb no respondio en {DISPLAY}")


def main():
    seed_help()
    start_xvfb()
    device.start(camera.start(RUN_DIR))
    screen.wait_for_window()
    screen.start()
    webui.start(PORT)
    screen.run()


if __name__ == "__main__":
    main()
