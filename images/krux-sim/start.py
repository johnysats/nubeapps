#!/usr/bin/env python3
"""Punto de entrada del contenedor: arranca el firmware de Krux headless.

Reproduce el orden de importacion de `simulator/simulator.py` de upstream (los mocks se
instalan en sys.modules y el orden importa), pero sin ventana SDL: la pantalla se publica
por HTTP y los controles llegan por POST. Ver kxemu/__init__.py.
"""
import os
import sys
import threading

KRUX_DIR = os.environ.get("KXEMU_KRUX_DIR", "/krux")
DATA_DIR = os.environ.get("KXEMU_DATA_DIR", "/data")
SD_DIR = os.environ.get("KXEMU_SD_DIR", "/data/sd")
DEVICE = os.environ.get("KXEMU_DEVICE", "maixpy_amigo")
PORT = int(os.environ.get("KXEMU_PORT", "6080"))

sys.path.insert(0, os.path.join(KRUX_DIR, "src"))
sys.path.insert(0, os.path.join(KRUX_DIR, "simulator"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# El simulador de upstream espera correr desde simulator/ (busca ahi assets/, ../src/boot.py
# y las fuentes .bdf). Krux, en cambio, guarda en rutas relativas al cwd: "sd" es la MicroSD
# y "flash" la memoria interna. Se resuelve con symlinks a los volumenes en vez de mover
# ninguna de las dos convenciones.
os.chdir(os.path.join(KRUX_DIR, "simulator"))
for link, target in (("sd", SD_DIR), ("flash", os.path.join(DATA_DIR, "flash"))):
    os.makedirs(target, exist_ok=True)
    if not os.path.islink(link):
        os.symlink(target, link)

import pygame as pg

# Los mocks se apropian de nombres de modulos del firmware, y "qrcode" es uno de ellos:
# se guarda antes la libreria de PyPI, que es la que dibuja los QR de la camara virtual.
import qrcode

sys.modules["kxemu_qrcode"] = qrcode

pg.init()
pg.freetype.init()

from kruxsim.mocks import board

board.register_device(DEVICE)

# uopen/uos: redirigen las rutas /sd y /flash del firmware a las carpetas locales.
from kruxsim.mocks import uopen
from kruxsim.mocks import uos
from kruxsim.mocks import uos_functions
from kruxsim.mocks import ujson
from kruxsim.mocks import urandom
from kruxsim.mocks import usys
from kruxsim.mocks import utime
from kruxsim.mocks import fpioa_manager
from kruxsim.mocks import Maix
from kruxsim.mocks import flash
from kruxsim.mocks import lcd
from kruxsim.mocks import machine
from kruxsim.mocks import image
from kruxsim.mocks import pmu
from kruxsim.mocks import deflate
from kruxsim.mocks import secp256k1
from kruxsim.mocks import qrcode
from kruxsim.mocks import sensor
from kruxsim.mocks import shannon
from kruxsim.mocks import ft6x36
from kruxsim.mocks import gt911
from kruxsim.mocks import cst816
from kruxsim.mocks import buttons
from kruxsim.mocks import rotary
from kruxsim.mocks import uhashlib_hw
from kruxsim.mocks import baseconv
from kruxsim.mocks import sd_card

from kxemu import remote, screen, webui

remote.install()
display = screen.start(DEVICE)
webui.start(PORT)


def run_krux():
    with open("../src/boot.py", "r", encoding="utf-8") as boot_file:
        exec(boot_file.read())  # pylint: disable=exec-used


threading.Thread(target=run_krux, daemon=True).start()

screen.run(display, DEVICE, remote.remote)
