"""Camara virtual: un archivo de la MicroSD servido como QR.

El navegador solo entrega la webcam por HTTPS o localhost y Umbrel sirve las apps por HTTP
en la LAN, asi que aca no hay camara real: la "escena" que ve el dispositivo es un archivo
elegido de la carpeta compartida, codificado en el formato que el firmware espera.

`data_codecs/qr_factory.py` del firmware reconoce, en este orden, UR2, UR1, QR pelado y
—solo si la pantalla lo pide explicitamente— SeedQR:

| Archivo | Que se le muestra |
|---|---|
| PSBT (binario o base64) | UR `crypto-psbt` animado, una parte por frame |
| texto de 12 o 24 palabras BIP39 | SeedQR numerico (4 digitos por palabra) |
| cualquier otro texto | QR de una sola parte con el texto tal cual |
"""
import base64
import logging
import os
import threading

import numpy as np
import qrcode
from PIL import Image
from mnemonic import Mnemonic
from ur.ur import UR
from ur.ur_encoder import UREncoder
from urtypes.crypto import PSBT as UR_PSBT

logger = logging.getLogger(__name__)

# Lo que el firmware recibe por el pipe de la camara: el recorte ya escalado que en el
# dispositivo real sale del sensor (`CameraSimulator.capture()` de upstream).
CAMERA_SIZE = (396, 330)
MAX_UR_FRAGMENT = 200  # bytes por parte; mas grande, el QR se vuelve ilegible

_BLANK = None


def _blank():
    global _BLANK
    if _BLANK is None:
        _BLANK = _to_rgb565(Image.new("L", CAMERA_SIZE, 255).convert("RGB"))
    return _BLANK


def _to_rgb565(image):
    """RGB de 8 bits a los dos bytes por pixel que lee el firmware, byte bajo primero."""
    array = np.asarray(image, dtype=np.uint16)
    packed = ((array[:, :, 0] & 0xF8) << 8) | ((array[:, :, 1] & 0xFC) << 3) | (array[:, :, 2] >> 3)
    return packed.astype("<u2").tobytes()


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
            return sorted(
                name for name in os.listdir(self.directory)
                if os.path.isfile(os.path.join(self.directory, name)) and not name.startswith(".")
            )
        except OSError:
            return []

    def select(self, name):
        # Solo el nombre: el `file=` viene del navegador y un "../" o una ruta absoluta
        # sacaria la camara de la carpeta compartida.
        with self._lock:
            self.selected = os.path.basename(name or "")
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
                data = base64.b64decode(data)
            encoder = UREncoder(UR("crypto-psbt", UR_PSBT(data).to_cbor()), MAX_UR_FRAGMENT)
            parts = [encoder.next_part().upper()
                     for _ in range(max(encoder.fountain_encoder.seq_len(), 1))]
            return Scene(parts, "psbt")

        text = data.decode("utf-8", errors="replace").strip()
        digits = _seedqr_digits(text)
        if digits:
            return Scene([digits], "seedqr")
        return Scene([text], "text")

    def next_frame(self) -> bytes:
        with self._lock:
            if self._scene is None:
                self._scene = self._build_scene()
            scene = self._scene
        if scene is None:
            return _blank()
        return _to_rgb565(_render(scene.next_part()))


def _render(payload):
    """El QR centrado en el frame, con modulos de un numero entero de pixeles.

    Reescalar un QR chico a un tamano que no sea multiplo exacto de su cuadricula deja los
    modulos de distinto ancho y el decodificador falla de a ratos, asi que el tamano del
    modulo se elige entero y el QR se centra en el sobrante.
    """
    code = qrcode.QRCode(border=2)
    code.add_data(payload)
    code.make(fit=True)
    modules = len(code.get_matrix())
    box = max(1, min(CAMERA_SIZE) // modules)
    image = code.make_image(fill_color="black", back_color="white").convert("RGB")
    image = image.resize((modules * box, modules * box), Image.NEAREST)
    frame = Image.new("RGB", CAMERA_SIZE, "white")
    frame.paste(image, ((CAMERA_SIZE[0] - image.width) // 2, (CAMERA_SIZE[1] - image.height) // 2))
    return frame


source = None


def init(directory):
    global source
    source = Source(directory)
    return source
