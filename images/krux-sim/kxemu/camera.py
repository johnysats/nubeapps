"""Camara virtual: la "escena" que ve el Krux es un archivo de la SD emulada.

En un contenedor no hay webcam (el mock de upstream abre `VideoCapture(0)`), asi que el
archivo elegido en la pagina se codifica como QR -- animado en partes `pXofN` si es un
PSBT -- y se entrega como frames de video. El flujo del dispositivo real no cambia: entras
a "Scan" y ves el QR.
"""
import base64
import binascii
import os
import sys
import threading
import time

import numpy as np
from PIL import Image, ImageDraw

# `kruxsim.mocks.qrcode` reemplaza sys.modules["qrcode"] por el modulo del firmware (el que
# usa el dispositivo para dibujar sus propios QR). start.py guarda antes la libreria de PyPI
# bajo otro nombre; sin eso, aca importariamos el mock y todo devolveria MagicMocks.
qrcode = sys.modules.get("kxemu_qrcode")
if qrcode is None:  # importado fuera del simulador (pruebas sueltas)
    import qrcode

FRAME_SIDE = 480
# El QR ocupa una parte del cuadro: el preview del dispositivo recorta el frame al aspecto
# de su pantalla, y asi entra entero en la vista previa (el decodificado usa el frame full).
QR_SIDE = 300
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PSBT_MAGIC = b"psbt\xff"
# Bytes por parte de un QR animado: ~240 entra en un QR version 11 y sobra margen para que
# pyzbar lo lea a QR_SIDE pixeles.
PART_SIZE = 240
# Un dispositivo real muestra un QR animado a ~5 fps; el decoder no sigue mucho mas rapido.
PART_INTERVAL = 0.2


class SourceSelector:
    """A que archivo de la carpeta compartida esta "apuntando" la camara.

    Las rutas se manejan como str y no con pathlib: el mock `uos` de upstream parchea
    os.stat() para reescribir las rutas /sd del firmware, y ahi un PosixPath revienta.
    """

    def __init__(self, directory):
        self.directory = directory
        self.selected = None  # None = automatico (el mas reciente)
        self._lock = threading.Lock()

    def list_files(self):
        """Nombres de la carpeta, del mas reciente al mas viejo."""
        if not os.path.isdir(self.directory):
            return []
        names = [
            name
            for name in os.listdir(self.directory)
            if not name.startswith(".") and os.path.isfile(os.path.join(self.directory, name))
        ]
        return sorted(
            names,
            key=lambda name: os.path.getmtime(os.path.join(self.directory, name)),
            reverse=True,
        )

    def select(self, name):
        # Solo el nombre: el `file=` viene del navegador y un "../" o una ruta absoluta
        # sacaria la camara de la carpeta compartida.
        with self._lock:
            self.selected = os.path.basename(name) if name else None

    def resolve(self):
        """Ruta completa del archivo que ve la camara, o None si no hay ninguno."""
        with self._lock:
            selected = self.selected
        if selected:
            path = os.path.join(self.directory, selected)
            if os.path.isfile(path):
                return path
        names = self.list_files()
        return os.path.join(self.directory, names[0]) if names else None


source = SourceSelector(os.environ.get("KXEMU_SD_DIR", "/data/sd"))


def _in_entropy_capture():
    """True si quien pide el frame es la pantalla de entropia por camara.

    No espera ningun QR: quiere una escena con variacion de pixeles. La resolucion no la
    distingue (scan y entropia piden lo mismo), asi que se mira quien esta llamando.
    """
    frame = sys._getframe(1)
    for _ in range(12):
        if frame is None:
            return False
        if frame.f_code.co_filename.endswith("pages/capture_entropy.py"):
            return True
        frame = frame.f_back
    return False


def _parts(path):
    """(partes de texto a mostrar como QR, mensaje de error)."""
    with open(path, "rb") as source_file:
        raw = source_file.read()
    name = os.path.basename(path)

    payload = None
    if raw[:5] == PSBT_MAGIC:
        payload = base64.b64encode(raw).decode()
    else:
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return [], f"{name}: binario no reconocido"
        if text.startswith("cHNidP"):
            try:
                base64.b64decode(text, validate=True)
            except binascii.Error:
                return [], f"{name}: base64 invalido"
            payload = text
        else:
            # Descriptor, xpub, direccion, mensaje, mnemonic...: un QR estatico.
            return [text] if len(text) <= PART_SIZE else _split(text), None

    return _split(payload), None


def _split(payload: str):
    """Formato pXofN de krux: el mismo que usa el firmware para sus propios QR animados."""
    total = max(1, -(-len(payload) // PART_SIZE))
    if total == 1:
        return [payload]
    return [
        "p%dof%d %s" % (i + 1, total, payload[i * PART_SIZE : (i + 1) * PART_SIZE])
        for i in range(total)
    ]


def _qr_image(data: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB").resize(
        (QR_SIDE, QR_SIDE), Image.NEAREST
    )


def _message_image(text: str) -> Image.Image:
    """Mensaje para el usuario dentro del frame (sin archivos, archivo ilegible...)."""
    image = Image.new("RGB", (FRAME_SIDE, FRAME_SIDE), (30, 30, 30))
    draw = ImageDraw.Draw(image)
    lines = []
    for paragraph in text.split("\n"):
        while len(paragraph) > 44:
            cut = paragraph.rfind(" ", 0, 44)
            lines.append(paragraph[: cut if cut > 0 else 44])
            paragraph = paragraph[(cut if cut > 0 else 44) :].lstrip()
        lines.append(paragraph)
    y = FRAME_SIDE // 2 - len(lines) * 7
    for line in lines:
        draw.text((24, y), line, fill=(230, 230, 230))
        y += 14
    return image


def _centered(content: Image.Image) -> Image.Image:
    content = content.copy()
    content.thumbnail((FRAME_SIDE, FRAME_SIDE))
    frame = Image.new("RGB", (FRAME_SIDE, FRAME_SIDE), "white")
    frame.paste(content, ((FRAME_SIDE - content.width) // 2, (FRAME_SIDE - content.height) // 2))
    return frame


def _to_bgr(image: Image.Image):
    """El mock de `sensor` trata el frame como lo entrega OpenCV: BGR."""
    return np.asarray(image, dtype=np.uint8)[:, :, ::-1].copy()


class VirtualCamera:
    def __init__(self):
        self._path = None
        self._parts = []
        self._image = None
        self._error = None
        self._index = 0
        self._shown_at = 0.0
        self._cached = None

    def _load(self, path):
        self._path = path
        self._parts, self._image, self._error, self._index, self._cached = [], None, None, 0, None
        if path is None:
            self._error = "Sin archivos.\nSubi un PSBT o un descriptor en /files"
            return
        try:
            if os.path.splitext(path)[1].lower() in IMAGE_SUFFIXES:
                self._image = Image.open(path).convert("RGB")
                return
            self._parts, self._error = _parts(path)
            if self._error:
                self._parts = []
        except Exception as e:  # archivo borrado a mitad, permisos, imagen corrupta...
            self._error = f"{os.path.basename(path)}: {e}"

    def consumed(self):
        """El firmware decodifico la parte actual: pasamos a la siguiente."""
        if self._parts:
            self._index = (self._index + 1) % len(self._parts)
            self._cached = None

    def frame(self):
        if _in_entropy_capture():
            # La entropia sale de os.urandom, no de una escena real. Es un simulador: la
            # seed que genere no debe usarse nunca con fondos.
            noise = np.frombuffer(os.urandom(FRAME_SIDE * FRAME_SIDE * 3), dtype=np.uint8)
            return noise.reshape(FRAME_SIDE, FRAME_SIDE, 3).copy()

        path = source.resolve()
        if path != self._path:
            # Cambiaron el archivo desde la pagina con la pantalla de Scan abierta.
            self._load(path)

        now = time.monotonic()
        # `_cached is None` = la parte actual todavia no se mostro (recien cargada o recien
        # decodificada). Sin esa guarda se avanzaba dos veces por cada parte que el firmware
        # decodificaba, salteando la siguiente: un PSBT tardaba el doble de vueltas.
        if self._cached is not None and len(self._parts) > 1 and now - self._shown_at >= PART_INTERVAL:
            self._index = (self._index + 1) % len(self._parts)
            self._cached = None

        if self._cached is None:
            if self._image is not None:
                image = _centered(self._image)
            elif self._parts:
                image = _centered(_qr_image(self._parts[self._index]))
            else:
                image = _message_image(self._error or "Sin archivos")
            self._cached = _to_bgr(image)
            self._shown_at = now
        return self._cached


_camera = VirtualCamera()


def frame():
    return _camera.frame()


def consumed():
    _camera.consumed()
