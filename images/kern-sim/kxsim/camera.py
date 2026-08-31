"""Camara virtual: la "escena" que ve el Kern es un archivo de la MicroSD emulada.

El archivo elegido en la pagina se codifica como QR -- animado en partes `pXofN` si es un
PSBT -- y se publica como frames RGB565 que lee el driver de camara (kxsim/v4l2_capture.c).
El flujo del dispositivo no cambia: entras a "Scan" y ves el QR.

El modo ruido es un boton de la pagina, no una deteccion automatica: a diferencia de krux y
seedsigner, aca el firmware corre en otro proceso y no hay pila de llamadas para mirar. La
pantalla de entropia por camara mide variacion de pixeles y un QR no le sirve.
"""
import base64
import binascii
import os
import struct
import threading
import time

import qrcode
from PIL import Image, ImageDraw

# Resolucion de la camara virtual: tiene que ser exactamente la del preview del board.
#
# Antes de decodificar, el firmware recorta y escala el frame con el PPA del ESP32-P4, pero
# `ppa_do_scale_rotate_mirror()` en el simulador de upstream es un memcpy que no transforma
# nada. Publicando cualquier otro tamano, el decodificador reinterpreta nuestros bytes con
# otra geometria y los QR densos salen ilegibles ("Unrecognized format"). Con el tamano del
# preview el recorte queda en 1:1 y el memcpy es la identidad.
#
# 600x600 es el de wave_4b (main/qr/scanner.c: crop 960, escala 10/16 sobre una pantalla de
# 720). Si algun dia se empaqueta otro board hay que recalcularlo: wave_35 usa 320x320.
FRAME_WIDTH = 600
FRAME_HEIGHT = 600
QR_SIDE = 460

MAGIC = b"KRNF"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PSBT_MAGIC = b"psbt\xff"
# Bytes por parte de un QR animado: ~240 entra en un QR version 11 con margen de sobra para
# que el decodificador del firmware lo lea a QR_SIDE pixeles.
PART_SIZE = 240
# Un dispositivo real muestra un QR animado a ~5 fps; el decodificador no sigue mucho mas.
PART_INTERVAL = 0.2
# Se republica el mismo frame a este ritmo aunque no haya cambiado: el driver espera un seq
# nuevo, y sin esto el preview de la camara se veria congelado entre parte y parte.
PUBLISH_INTERVAL = 0.1


class SourceSelector:
    """A que archivo de la carpeta compartida esta "apuntando" la camara."""

    def __init__(self, directory):
        self.directory = directory
        self.selected = None  # None = automatico (el mas reciente)
        self.noise = False  # modo ruido, para la captura de entropia
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

    def set_noise(self, noise):
        with self._lock:
            self.noise = bool(noise)

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


source = SourceSelector(os.environ.get("KXSIM_SD_DIR", "/data/sdcard"))


def _parts(path):
    """(partes de texto a mostrar como QR, mensaje de error)."""
    with open(path, "rb") as source_file:
        raw = source_file.read()
    name = os.path.basename(path)

    if raw[:5] == PSBT_MAGIC:
        return _split(base64.b64encode(raw).decode()), None

    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return [], f"{name}: binario no reconocido"

    if text.startswith("cHNidP"):
        try:
            base64.b64decode(text, validate=True)
        except binascii.Error:
            return [], f"{name}: base64 invalido"
        return _split(text), None

    # Descriptor, xpub, direccion, mensaje, mnemonic...: un QR estatico si entra.
    return [text] if len(text) <= PART_SIZE else _split(text), None


def _split(payload: str):
    """Formato pXofN, el mismo que el firmware usa para sus propios QR animados."""
    total = max(1, -(-len(payload) // PART_SIZE))
    if total == 1:
        return [payload]
    return [
        "p%dof%d %s" % (i + 1, total, payload[i * PART_SIZE : (i + 1) * PART_SIZE])
        for i in range(total)
    ]


def _qr_image(data: str) -> Image.Image:
    """QR con modulos de un numero entero de pixeles.

    Nada de dibujarlo chico y reescalarlo despues: a un tamano que no sea multiplo exacto de
    la cuadricula, los modulos quedan de 7 y 8 pixeles alternados y el decodificador del
    firmware falla de a ratos (lee mal una parte de cada tantas y la rechaza entera).
    """
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    qr.box_size = max(1, QR_SIDE // (qr.modules_count + 2 * qr.border))
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _message_image(text: str) -> Image.Image:
    """Mensaje para el usuario dentro del frame (sin archivos, archivo ilegible...)."""
    image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (30, 30, 30))
    draw = ImageDraw.Draw(image)
    lines = []
    for paragraph in text.split("\n"):
        while len(paragraph) > 44:
            cut = paragraph.rfind(" ", 0, 44)
            lines.append(paragraph[: cut if cut > 0 else 44])
            paragraph = paragraph[(cut if cut > 0 else 44) :].lstrip()
        lines.append(paragraph)
    y = FRAME_HEIGHT // 2 - len(lines) * 7
    for line in lines:
        draw.text((24, y), line, fill=(230, 230, 230))
        y += 14
    return image


def _centered(content: Image.Image) -> Image.Image:
    content = content.copy()
    content.thumbnail((FRAME_WIDTH, FRAME_HEIGHT))
    frame = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), "white")
    frame.paste(content, ((FRAME_WIDTH - content.width) // 2, (FRAME_HEIGHT - content.height) // 2))
    return frame


class VirtualCamera:
    """Publica frames en un archivo que lee el driver de camara del simulador."""

    def __init__(self, path):
        self.path = path
        self._seq = 0
        self._source_path = None
        self._parts = []
        self._image = None
        self._error = None
        self._index = 0
        self._advanced_at = 0.0
        self._payload = None

    def _load(self, path):
        self._source_path = path
        self._parts, self._image, self._error, self._index, self._payload = [], None, None, 0, None
        if path is None:
            self._error = "Sin archivos.\nSubi un PSBT o una seed en /files"
            return
        try:
            if os.path.splitext(path)[1].lower() in IMAGE_SUFFIXES:
                self._image = Image.open(path).convert("RGB")
                return
            self._parts, self._error = _parts(path)
            if self._error:
                self._parts = []
        except OSError as error:  # archivo borrado a mitad, permisos, imagen corrupta...
            self._error = f"{os.path.basename(path)}: {error}"

    def _render(self):
        if source.noise:
            # La entropia sale de os.urandom, no de una escena real. Es un simulador: la
            # seed que genere no debe usarse nunca con fondos.
            return os.urandom(FRAME_WIDTH * FRAME_HEIGHT * 3)

        path = source.resolve()
        if path != self._source_path:
            # Cambiaron el archivo desde la pagina con la pantalla de Scan abierta.
            self._load(path)

        now = time.monotonic()
        if len(self._parts) > 1 and now - self._advanced_at >= PART_INTERVAL:
            self._index = (self._index + 1) % len(self._parts)
            self._advanced_at = now
            self._payload = None

        if self._payload is None:
            if self._image is not None:
                image = _centered(self._image)
            elif self._parts:
                image = _centered(_qr_image(self._parts[self._index]))
            else:
                image = _message_image(self._error or "Sin archivos")
            # RGB888 crudo: el empaquetado a RGB565 lo hace el driver en C. Pillow no trae
            # packer a 565 y hacerlo a mano en Python son 230.000 iteraciones por frame.
            self._payload = image.tobytes()
        return self._payload

    def publish(self):
        """Escribe el frame actual. El rename es atomico: el driver nunca lee uno a medias."""
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        header = struct.pack("<4sIII", MAGIC, FRAME_WIDTH, FRAME_HEIGHT, self._seq)
        temporary = self.path + ".tmp"
        # /run es tmpfs: el frame no toca el disco del usuario.
        with open(temporary, "wb") as frame_file:
            frame_file.write(header)
            frame_file.write(self._render())
        os.replace(temporary, self.path)

    def run(self):
        while True:
            try:
                self.publish()
            except OSError as error:
                print("kxsim: no pude publicar el frame de la camara:", error)
            time.sleep(PUBLISH_INTERVAL)


_camera = None


def start(run_dir):
    """Arranca el publicador de frames y devuelve la ruta que se le pasa a --webcam."""
    global _camera
    os.makedirs(run_dir, exist_ok=True)
    _camera = VirtualCamera(os.path.join(run_dir, "camera.rgb565"))
    _camera.publish()  # el primer frame antes de que el firmware abra la camara
    threading.Thread(target=_camera.run, daemon=True).start()
    return _camera.path
