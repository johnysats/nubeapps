#!/usr/bin/env python3
"""Arranca el firmware simulado y la carcasa web.

El binario del firmware corre como hijo de este proceso: si se cae, se cae el contenedor y
Docker lo reinicia, en vez de dejar una pantalla congelada.
"""
import logging
import os
import shutil
import signal
import sys

from pxemu import camera, device as device_module, webui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pxemu")

BINARY = "/app/passport-mpy"
BOOT_SCRIPT = "/app/simulator/sim_boot.py"
MODULE_PATH = ["/app/simulator/sim_modules", "/app/modules", "/app/extmod"]
HELP_DIR = "/app/help"
DATA_DIR = os.environ.get("PASSPORT_DATA_DIR", "/data")
WEB_PORT = int(os.environ.get("PASSPORT_WEB_PORT", "6080"))

# El firmware guarda y lee todo lo suyo en rutas relativas al directorio de trabajo:
# `microsd/` es la tarjeta y `settings.json` la memoria del dispositivo.
WORK_DIR = os.path.join(DATA_DIR, "work")
MICROSD_DIR = os.path.join(WORK_DIR, "microsd")


def seed_help_files(directory):
    """LEEME + seed de ejemplo la primera vez: una carpeta vacia no dice como se usa.

    Solo si no hay ningun archivo: si el usuario ya guardo lo suyo (o borro el LEEME),
    esto no vuelve a aparecer.
    """
    try:
        if any(not name.startswith(".") for name in os.listdir(directory)):
            return
        for name in os.listdir(HELP_DIR):
            shutil.copyfile(os.path.join(HELP_DIR, name), os.path.join(directory, name))
    except OSError as error:
        logger.warning("pxemu: no pude dejar la ayuda en %s: %s", directory, error)


def main():
    os.makedirs(MICROSD_DIR, exist_ok=True)
    if os.path.isdir(HELP_DIR):
        seed_help_files(MICROSD_DIR)

    source = camera.init(MICROSD_DIR)
    dev = device_module.Device(BINARY, BOOT_SCRIPT, MODULE_PATH, WORK_DIR, source)
    dev.start()
    webui.start(WEB_PORT, dev, source)

    def terminate(*_):
        dev.process.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    code = dev.wait()
    logger.error("pxemu: el firmware termino con %s", code)
    sys.exit(code or 1)


if __name__ == "__main__":
    main()
