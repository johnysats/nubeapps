"""Camara virtual: un archivo de /files servido como QR.

El navegador solo entrega la webcam por HTTPS o localhost, y Umbrel sirve las apps por HTTP
en la LAN, asi que la pagina de upstream (`getUserMedia`) no sirve aca. En vez de una camara
real, la "escena" que ve el dispositivo es un archivo elegido en /files, codificado en el
formato que el firmware espera para cada cosa:

| Archivo | Que se le muestra |
|---|---|
| PSBT (binario o base64) | UR `crypto-psbt` animado, una parte por frame |
| texto de 12 o 24 palabras BIP39 | SeedQR numerico (4 digitos por palabra) |
| cualquier otro texto | QR de una sola parte con el texto tal cual |
"""
import logging
import os
import threading

import qrcode
from PIL import Image
from mnemonic import Mnemonic
from ur.ur_encoder import UREncoder
from ur.ur import UR
from urtypes.crypto import PSBT as UR_PSBT

logger = logging.getLogger(__name__)

CAMERA_SIZE = (320, 240)
QR_SIDE = 220  # el QR ocupa el alto del frame menos un margen, como una foto de cerca
MAX_UR_FRAGMENT = 200  # bytes por parte: mas grande, el QR se vuelve ilegible al escalarlo

_BLANK = Image.new("L", CAMERA_SIZE, 255).tobytes()


def _is_psbt(data: bytes) -> bool:
    return data[:5] == b"psbt\xff" or data[:6] == b"cHNidP"


def _seedqr_digits(text: str):
    """Indices BIP39 en 4 digitos, o None si el texto no es un mnemonico."""
    words = text.split()
    if len(words) not in (12, 24):
        return None
    wordlist = Mnemonic("english").wordlist
    try:
        return "".join(f"{wordlist.index(word.lower()):04d}" for word in words)
    except ValueError:
        return None


class Scene:
    """Las partes ya codificadas de un archivo, y por cual va la animacion."""

    def __init__(self, parts, kind):
        self.parts = parts
        self.kind = kind
        self._index = 0

    def next_part(self):
        part = self.parts[self._index % len(self.parts)]
        self._index += 1
        return part


class Source:
    def __init__(self, directory):
        self.directory = directory
        self.selected = ""
        self._scene = None
        self._lock = threading.Lock()

    def list_files(self):
        try:
            entries = sorted(
                name for name in os.listdir(self.directory)
                if os.path.isfile(os.path.join(self.directory, name)) and not name.startswith(".")
            )
        except OSError:
            return []
        return entries

    def select(self, name):
        with self._lock:
            self.selected = name
            self._scene = None

    def resolve(self):
        if not self.selected:
            return None
        path = os.path.join(self.directory, self.selected)
        return path if os.path.isfile(path) else None

    def _build_scene(self):
        path = self.resolve()
        if not path:
            return None
        with open(path, "rb") as handle:
            data = handle.read()

        if _is_psbt(data):
            if data[:6] == b"cHNidP":
                import base64
                data = base64.b64decode(data)
            ur = UR("crypto-psbt", UR_PSBT(data).to_cbor())
            encoder = UREncoder(ur, MAX_UR_FRAGMENT)
            # Una vuelta completa: con fountain codes el firmware necesita al menos las
            # partes puras, y repetirlas en orden alcanza para que arme el PSBT.
            parts = [encoder.next_part().upper() for _ in range(max(encoder.fountain_encoder.seq_len(), 1))]
            return Scene(parts, "psbt")

        text = data.decode("utf-8", errors="replace").strip()
        digits = _seedqr_digits(text)
        if digits:
            return Scene([digits], "seedqr")
        return Scene([text], "text")

    def next_frame(self) -> bytes:
        """Un frame de 320x240 en escala de grises, listo para el firmware."""
        with self._lock:
            if self._scene is None:
                self._scene = self._build_scene()
            scene = self._scene
        if scene is None:
            return _BLANK
        qr = qrcode.make(scene.next_part(), border=2).convert("L")
        qr = qr.resize((QR_SIDE, QR_SIDE), Image.NEAREST)
        frame = Image.new("L", CAMERA_SIZE, 255)
        frame.paste(qr, ((CAMERA_SIZE[0] - QR_SIDE) // 2, (CAMERA_SIZE[1] - QR_SIDE) // 2))
        return frame.tobytes()


source = None


def init(directory):
    global source
    source = Source(directory)
    return source
