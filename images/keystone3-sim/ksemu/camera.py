"""Camara virtual: lo que "ve" el Keystone es un archivo de la MicroSD emulada.

Aca no hay imagenes ni QR dibujados. El simulador de upstream, compilado sin
`GET_QR_DATA_FROM_SCREEN` (ver ../patches/LEEME.md), lee `assets/qrcode_data.txt` cuando
entras a la pantalla de escaneo y toma **cada linea como un QR ya decodificado**: se las pasa
tal cual a su parser de UR. Asi que la camara de ksemu es solo un traductor de "el usuario
eligio este archivo" a esas lineas.

Como llega decodificado no hay tamano maximo de QR ni hace falta animar nada: el PSBT va en
un solo UR mientras entre en un fragmento (`FRAGMENT`), que es el caso normal. El limite real
lo pone el firmware: 100 KB de archivo y 3000 lineas.

**El orden importa y no se puede evitar**: el firmware lee el archivo al abrir la pantalla de
escaneo, una sola vez. Primero se elige el archivo en la pagina, despues se entra a escanear
en el dispositivo. Esta dicho en la carcasa y en el LEEME de la MicroSD.
"""
import base64
import binascii
import os
import threading

from ur.cbor_lite import CBOREncoder
from ur.ur import UR
from ur.ur_encoder import UREncoder

PSBT_MAGIC = b"psbt\xff"
# Un fragmento de este tamano deja el PSBT tipico en una sola parte. Solo importa para no
# quedarse sin memoria: el "QR" nunca se dibuja, asi que no hay una version de QR que llenar.
FRAGMENT = 20000

ASSETS_DIR = os.environ.get("KSEMU_ASSETS_DIR", "/data/assets")
QR_FILE = os.path.join(ASSETS_DIR, "qrcode_data.txt")


class SourceSelector:
    """A que archivo de la carpeta compartida esta "apuntando" la camara."""

    def __init__(self, directory):
        self.directory = directory
        self.selected = None
        self.error = None
        self.parts = 0
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

        def mtime(name):  # el archivo puede desaparecer desde /files entre el listado y el orden
            try:
                return os.path.getmtime(os.path.join(self.directory, name))
            except OSError:
                return 0.0

        return sorted(names, key=mtime, reverse=True)

    def select(self, name):
        # Solo el nombre: el `file=` viene del navegador y un "../" o una ruta absoluta
        # sacaria la camara de la carpeta compartida.
        with self._lock:
            self.selected = os.path.basename(name) if name else None
            self.error = None
            self.parts = 0
            path = self.resolve()
            if path is None:
                _write([])
                return
            try:
                lines = _lines(path)
            except (OSError, ValueError) as error:
                self.error = str(error)
                _write([])
                return
            self.parts = len(lines)
            _write(lines)

    def resolve(self):
        """Ruta completa del archivo que ve la camara, o None si no hay ninguno."""
        if not self.selected:
            return None
        path = os.path.join(self.directory, self.selected)
        return path if os.path.isfile(path) else None


source = SourceSelector(os.environ.get("KSEMU_SD_DIR", "/data/assets/sd"))


def _lines(path):
    """Las lineas que el firmware va a leer como QR sucesivos."""
    with open(path, "rb") as handle:
        raw = handle.read()
    name = os.path.basename(path)

    if raw[:5] == PSBT_MAGIC:
        return _ur_psbt(raw)

    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ValueError(f"{name}: binario no reconocido (no es un PSBT)")

    if text.startswith("cHNidP"):
        # Sin los blancos: los exportadores cortan el base64 en lineas de 64 y `validate`
        # no tolera un salto de linea en el medio.
        try:
            return _ur_psbt(base64.b64decode("".join(text.split()), validate=True))
        except binascii.Error:
            raise ValueError(f"{name}: parece un PSBT en base64, pero no es base64 valido")

    # Cualquier otra cosa -un UR ya armado, un xpub, un descriptor, una direccion- va tal
    # cual, una linea por QR. Las lineas vacias y los comentarios se descartan para poder
    # anotar el archivo, igual que en ccq1.
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        raise ValueError(f"{name}: el archivo esta vacio")
    return lines


def _ur_psbt(raw):
    encoder = CBOREncoder()
    encoder.encodeBytes(raw)
    ur_encoder = UREncoder(UR("crypto-psbt", encoder.get_bytes()), FRAGMENT)
    # seq_len() es 1 cuando entra en un fragmento; con mas, las partes 1..N son las que el
    # firmware necesita para reconstruirlo (despues repite hasta completar, pero no hace
    # falta darle mas).
    return [ur_encoder.next_part().upper()
            for _ in range(max(ur_encoder.fountain_encoder.seq_len(), 1))]


def _write(lines):
    """Deja el archivo que lee el firmware. Atomico: lo puede estar leyendo justo ahora."""
    temporary = QR_FILE + ".tmp"
    with open(temporary, "w") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))
    os.replace(temporary, QR_FILE)


def start():
    """Arranca sin ninguna escena: la pantalla de escaneo no ve nada hasta que se elija."""
    try:
        _write([])
    except OSError as error:
        print("ksemu: no pude preparar el archivo de la camara:", error)
    return source
