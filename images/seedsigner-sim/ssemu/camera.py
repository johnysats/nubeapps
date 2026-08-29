"""Camara virtual: el "mundo" que ve el SeedSigner es un archivo de la MicroSD.

SeedSigner no tiene E/S por archivos: todo entra por la camara escaneando QRs. Como en
un contenedor no hay webcam, el archivo que elegis en la pagina (o el mas reciente de la
carpeta) se codifica como QR -- animado si es un PSBT -- y se sirve como frames de video.
El resultado es el flujo real del dispositivo: entras a Scan y "ves" el QR.
"""
import base64
import binascii
import logging
import os
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import qrcode
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PSBT_MAGIC = b"psbt\xff"

# Cada cuanto avanza el QR animado. Un dispositivo real mostrando un UR fountain va a
# ~5 fps; mas rapido que eso el decoder pierde frames.
PART_INTERVAL = 0.2


class SourceSelector:
    """A que archivo de la carpeta compartida esta "apuntando" la camara."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.selected = None  # None = automatico (el mas reciente)
        self._lock = threading.Lock()

    def list_files(self):
        if not self.directory.is_dir():
            return []
        files = [p for p in self.directory.iterdir() if p.is_file() and not p.name.startswith(".")]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def select(self, name):
        # Solo el nombre: el `file=` viene del navegador y un "../" o una ruta absoluta
        # sacaria la camara de la carpeta compartida.
        with self._lock:
            self.selected = Path(name).name if name else None

    def resolve(self):
        with self._lock:
            selected = self.selected
        if selected:
            path = self.directory / selected
            if path.is_file():
                return path
        files = self.list_files()
        return files[0] if files else None


source = SourceSelector(Path(os.environ.get("SSEMU_SD_DIR", "/data/MicroSD")))


def _qr_image(data: str, side: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((side, side), Image.NEAREST)


def _message_image(text: str, side: int) -> Image.Image:
    """Mensaje para el usuario dentro del frame de la camara (sin archivo, error...).

    Se dibuja a 240 px -- el tamano real de la pantalla del dispositivo -- y recien
    despues se escala: la fuente por defecto de PIL es de 11 px fijos y a 480 px el
    texto quedaria ilegible cuando el device reduce el frame para la vista previa.
    """
    base = 240
    img = Image.new("RGB", (base, base), (32, 32, 32))
    draw = ImageDraw.Draw(img)
    lines = []
    for paragraph in text.split("\n"):
        while len(paragraph) > 34:
            cut = paragraph.rfind(" ", 0, 34)
            cut = cut if cut > 0 else 34
            lines.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        lines.append(paragraph)
    y = max(4, base // 2 - len(lines) * 7)
    for line in lines:
        draw.text((8, y), line, fill=(220, 220, 220))
        y += 14
    return img.resize((side, side), Image.NEAREST)


def _load_source(path: Path):
    """Devuelve ('image', PIL.Image) | ('encoder', encoder) | ('error', str)."""
    from seedsigner.models.encode_qr import GenericStaticQrEncoder, UrPsbtQrEncoder
    from seedsigner.models.settings import Settings
    from seedsigner.models.settings_definition import SettingsConstants

    if path.suffix.lower() in IMAGE_SUFFIXES:
        return "image", Image.open(path).convert("RGB")

    raw = path.read_bytes()
    density = Settings.get_instance().get_value(SettingsConstants.SETTING__QR_DENSITY)

    psbt_bytes = None
    if raw[:5] == PSBT_MAGIC:
        psbt_bytes = raw
    else:
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return "error", f"{path.name}: binario no reconocido"
        if text.startswith("cHNidP"):
            try:
                psbt_bytes = base64.b64decode(text)
            except binascii.Error:
                return "error", f"{path.name}: base64 invalido"
        else:
            # Descriptor, xpub, direccion, mnemonic...: QR estatico con el texto tal cual.
            return "encoder", GenericStaticQrEncoder(data=text, qr_density=density)

    from embit.psbt import PSBT

    try:
        psbt = PSBT.parse(psbt_bytes)
    except Exception as e:
        return "error", f"{path.name}: PSBT invalido ({e})"
    return "encoder", UrPsbtQrEncoder(psbt=psbt, qr_density=density)


class FileQRVideoStream:
    """Reemplazo de PiVideoStream: misma interfaz start()/read()/stop()."""

    def __init__(self, resolution=(320, 240), framerate=32, format="rgb", **kwargs):
        self.width, self.height = resolution
        self.frame = None
        self.should_stop = False
        self.is_stopped = True

        # La camara de un Pi entrega la escena; el frame se rota recien en
        # Camera.read_video_stream (90 + camera_rotation). Pre-rotamos al reves para que
        # los mensajes de texto se lean derechos en la pantalla del dispositivo.
        from seedsigner.models.settings import Settings
        from seedsigner.models.settings_definition import SettingsConstants

        rotation = int(Settings.get_instance().get_value(SettingsConstants.SETTING__CAMERA_ROTATION))
        self._pre_rotation = -(90 + rotation)

        # La pantalla de entropia por imagen no espera ningun QR: quiere una escena, y
        # le damos ruido. No se distingue por resolucion (scan y entropia piden las dos
        # un cuadrado), asi que miramos quien nos esta instanciando.
        self._entropy_mode = any(
            frame.filename.endswith("gui/screens/tools_screens.py")
            for frame in traceback.extract_stack()
        )

        self._path = None
        self._kind = None
        self._payload = None
        self._last_part = 0.0
        self._cached = None

    def start(self):
        self.is_stopped = False
        if not self._entropy_mode:
            self._load(source.resolve())
        return self

    def _load(self, path):
        self._path = path
        if path is None:
            self._kind, self._payload = "error", "Sin archivos.\nSubi un PSBT en /files"
            return
        try:
            self._kind, self._payload = _load_source(path)
        except Exception as e:
            logger.exception("ssemu: no se pudo leer la fuente de la camara")
            self._kind, self._payload = "error", f"{path.name}: {e}"

    def _content(self, side: int) -> Image.Image:
        if self._entropy_mode:
            return Image.fromarray(
                np.frombuffer(os.urandom(side * side * 3), dtype=np.uint8).reshape(side, side, 3)
            )
        if self._kind == "image":
            content = self._payload.copy()
            content.thumbnail((side, side))
            frame = Image.new("RGB", (side, side), "white")
            frame.paste(content, ((side - content.width) // 2, (side - content.height) // 2))
            return frame
        if self._kind == "encoder":
            return _qr_image(self._payload.next_part(), side)
        return _message_image(str(self._payload), side)

    def read(self):
        now = time.monotonic()
        resolved = None if self._entropy_mode else source.resolve()
        if not self._entropy_mode and resolved != self._path:
            # Cambiaron el archivo desde la pagina con la pantalla de Scan abierta:
            # apuntamos la camara al nuevo sin salir y volver a entrar.
            self._load(resolved)
            self._cached = None
        if self._cached is None or now - self._last_part >= PART_INTERVAL:
            side = min(self.width, self.height)
            content = self._content(side).rotate(self._pre_rotation, expand=True)
            frame = Image.new("RGB", (self.width, self.height), "white")
            frame.paste(content, ((self.width - content.width) // 2,
                                  (self.height - content.height) // 2))
            self._cached = np.asarray(frame, dtype=np.uint8)
            self._last_part = now
        return self._cached

    def stop(self):
        self.should_stop = True
        self.is_stopped = True


class PiCameraError(Exception):
    """Lo importa hardware/camera.py para distinguir fallos de conexion de la camara."""


class PiCamera:
    """Modo de un solo frame (entropia por imagen y vista previa de rotacion).

    La entropia sale de os.urandom, no de una escena real: es un simulador, la seed que
    genere no debe usarse nunca con fondos.
    """

    def __init__(self, resolution=(720, 480), framerate=24, **kwargs):
        self.resolution = resolution
        self.framerate = framerate
        self.shutter_speed = 0
        self.exposure_speed = 0
        self.exposure_mode = "auto"
        self.awb_gains = (1.0, 1.0)
        self.awb_mode = "auto"

    def start_preview(self):
        pass

    def capture(self, output, format="jpeg"):
        width, height = self.resolution
        noise = np.frombuffer(os.urandom(width * height * 3), dtype=np.uint8)
        image = Image.fromarray(noise.reshape(height, width, 3))
        image.save(output, format=format.upper())

    def close(self):
        pass
