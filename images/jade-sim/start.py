#!/usr/bin/env python3
"""Arranca el firmware emulado y la carcasa web.

qemu corre como hijo de este proceso: si el firmware se cae, se cae el contenedor y Docker
lo reinicia, en vez de dejar una pantalla congelada.
"""
import logging
import os
import shutil
import signal
import subprocess
import sys
import time

from jxemu import camera, device as device_module, webui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jxemu")

QEMU = "/app/qemu/bin/qemu-system-xtensa"
FLASH_IMAGE = "/app/flash_image.bin"
EFUSE_IMAGE = "/app/qemu_efuse.bin"
DATA_DIR = os.environ.get("JADE_DATA_DIR", "/data")
FILES_DIR = os.environ.get("JADE_FILES_DIR", "/data/files")
HELP_DIR = "/app/help"
WEB_PORT = int(os.environ.get("JADE_WEB_PORT", "6080"))


def qemu_command(flash, efuse):
    return [
        QEMU, "-nographic", "-machine", "esp32", "-m", "4M",
        "-drive", f"file={flash},if=mtd,format=raw",
        # El puerto 30121 (serial sobre TCP) queda dentro del contenedor a proposito: la app
        # es air-gapped y Umbrel solo publica el HTTP con su propia autenticacion.
        "-nic", "user,model=open_eth,id=lo0,hostfwd=tcp:127.0.0.1:30122-:30122",
        "-drive", f"file={efuse},if=none,format=raw,id=efuse",
        "-global", "driver=nvram.esp32.efuse,property=drive,value=efuse",
        "-serial", "null",
    ]


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
        logger.warning("jxemu: no pude dejar la ayuda en %s: %s", directory, error)


def main():
    os.makedirs(FILES_DIR, exist_ok=True)
    seed_help_files(FILES_DIR)
    # La flash y los efuses son el estado persistente del dispositivo: el PIN, la seed
    # cifrada y los ajustes viven ahi, asi que se copian una sola vez y se reusan.
    flash = os.path.join(DATA_DIR, "flash_image.bin")
    efuse = os.path.join(DATA_DIR, "qemu_efuse.bin")
    for source_path, target in ((FLASH_IMAGE, flash), (EFUSE_IMAGE, efuse)):
        if not os.path.exists(target):
            shutil.copyfile(source_path, target)

    qemu = subprocess.Popen(qemu_command(flash, efuse))
    logger.info("jxemu: qemu arrancado (pid %s)", qemu.pid)

    source = camera.init(FILES_DIR)
    dev = device_module.Device("ws://127.0.0.1:30122/ws", source)
    dev.start()
    webui.start(WEB_PORT, dev, source)

    def terminate(*_):
        qemu.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    while qemu.poll() is None:
        time.sleep(1)
    logger.error("jxemu: qemu termino con %s", qemu.returncode)
    sys.exit(qemu.returncode or 1)


if __name__ == "__main__":
    main()
