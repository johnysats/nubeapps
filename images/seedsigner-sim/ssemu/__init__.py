"""Shim para correr el firmware de SeedSigner sin Raspberry Pi.

Los tres puntos de contacto con el hardware (GPIO, display SPI, camara) se reemplazan
instalando modulos falsos en sys.modules antes de que seedsigner los importe. El arbol
de upstream queda intacto: se clona por tag y no se le aplica ningun parche.
"""
import logging
import os
import sys
import types

logger = logging.getLogger(__name__)


def install():
    _install_fake_gpio()
    _install_fake_camera()

    from ssemu import display, dump, webui

    display.install()
    dump.install()
    webui.start(int(os.environ.get("SSEMU_PORT", "6080")))


def _install_fake_gpio():
    from ssemu import fake_gpio

    rpi = types.ModuleType("RPi")
    rpi.GPIO = fake_gpio
    sys.modules["RPi"] = rpi
    sys.modules["RPi.GPIO"] = fake_gpio


def _install_fake_camera():
    from ssemu import camera

    picamera = types.ModuleType("picamera")
    picamera.PiCamera = camera.PiCamera
    picamera.PiCameraError = camera.PiCameraError
    sys.modules["picamera"] = picamera

    # hardware/camera.py hace `from seedsigner.hardware.pivideostream import PiVideoStream`
    # dentro de la funcion: alcanza con tener el modulo ya resuelto en sys.modules.
    pivideostream = types.ModuleType("seedsigner.hardware.pivideostream")
    pivideostream.PiVideoStream = camera.FileQRVideoStream
    sys.modules["seedsigner.hardware.pivideostream"] = pivideostream
