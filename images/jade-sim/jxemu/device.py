"""Cliente del WebSocket del firmware: pantalla, botones y camara.

Protocolo de `main/qemu/qemu_display.c`, un byte de comando por mensaje:

| Sentido | Codigo | Que es |
|---|---|---|
| pagina -> firmware | 0 | pedir el frame actual |
| pagina -> firmware | 1 / 3 | rueda a la izquierda / a la derecha |
| pagina -> firmware | 4 | boton frontal (seleccionar) |
| pagina -> firmware | 12 | trozo de frame de camara (320x240, 1 byte por pixel) |
| firmware -> pagina | 0 | trozo del framebuffer (RGB565, little endian) |
| firmware -> pagina | 1 / 2 | encender / apagar la camara |

La camara es *pull*: el firmware manda un 1 cada vez que quiere un frame y se queda
bloqueado en la cola hasta recibirlo (`esp_camera_fb_get`). Mandarle frames de motu proprio
le cuelga el servidor web dentro del dispositivo, asi que se responde uno por pedido.
"""
import asyncio
import logging
import threading

import numpy as np
import websockets
from PIL import Image

logger = logging.getLogger(__name__)

DISPLAY_SIZE = (320, 170)  # CONFIG_DISPLAY_WIDTH/HEIGHT del board QEMU_LARGER (= Jade Plus)
CAMERA_SIZE = (320, 240)  # CAMERA_IMAGE_WIDTH/HEIGHT de main/camera.h
MAX_WS_PAYLOAD = 16383  # QEMU_MAX_WS_SIZE, incluido el byte de comando

PROVIDE_DISPLAY = 0
LEFT_WHEEL = 1
WHEEL_CLICK = 2
RIGHT_WHEEL = 3
FRONT_BUTTON = 4
CAMERA_FRAME = 12

KEYS = {"prev": LEFT_WHEEL, "next": RIGHT_WHEEL, "select": FRONT_BUTTON}


class FrameBuffer:
    """Ultimo frame + numero de secuencia, para el long-poll de /frame.jpg."""

    def __init__(self, size):
        self._cond = threading.Condition()
        self._image = Image.new("RGB", size, "black")
        self._seq = 0

    def put(self, image):
        with self._cond:
            self._image = image
            self._seq += 1
            self._cond.notify_all()

    def current(self):
        with self._cond:
            return self._seq, self._image

    def wait_for_next(self, last_seq, timeout=5.0):
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self._image


def _rgb565_to_image(buf):
    """RGB565 big-endian (el orden en que lo escupe el ST7789) a RGB de 8 bits.

    Los dos detalles que no se pueden equivocar, o los colores dejan de ser los del
    dispositivo: los bytes vienen al reves de lo que asume numpy en little-endian (con el
    verde partido entre los dos bytes, asi que leerlo mal desteñe todo menos los grises), y
    los 5 o 6 bits de cada canal se estiran replicando los bits altos, no con un shift: 31
    tiene que dar 255 y no 248, si no la pantalla entera queda apagada.
    """
    width, height = DISPLAY_SIZE
    raw = np.frombuffer(buf, dtype=">u2").reshape(height, width)
    red5 = (raw >> 11) & 0x1F
    green6 = (raw >> 5) & 0x3F
    blue5 = raw & 0x1F
    red = (red5 << 3) | (red5 >> 2)
    green = (green6 << 2) | (green6 >> 4)
    blue = (blue5 << 3) | (blue5 >> 2)
    return Image.fromarray(np.dstack([red, green, blue]).astype("uint8"))


class Device:
    """Conexion al firmware emulado, viviendo en su propio hilo con su propio event loop."""

    def __init__(self, url, camera_source):
        self.url = url
        self.camera = camera_source
        self.framebuffer = FrameBuffer(DISPLAY_SIZE)
        self.camera_on = False
        self.connected = False
        self._loop = None
        self._ws = None
        self._ready = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=10)

    def press(self, key):
        """Encola una pulsacion desde el hilo del servidor web."""
        code = KEYS[key]
        if self._loop is None:
            return False
        asyncio.run_coroutine_threadsafe(self._send(bytes([code])), self._loop)
        return True

    async def _send(self, payload):
        if self._ws is not None:
            try:
                await self._ws.send(payload)
            except websockets.WebSocketException:
                pass

    async def _send_camera_frame(self):
        """Un frame por pedido: el firmware espera bloqueado hasta tenerlo entero."""
        payload = self.camera.next_frame()
        offset = 0
        while offset < len(payload):
            end = min(offset + MAX_WS_PAYLOAD - 1, len(payload))
            await self._send(bytes([CAMERA_FRAME]) + payload[offset:end])
            offset = end

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._reconnect_forever())

    async def _reconnect_forever(self):
        while True:
            try:
                await self._session()
            except Exception as exc:  # el firmware reinicia y se cae la conexion
                logger.info("jxemu: reconectando al firmware (%s)", exc)
                self.connected = False
                self._ws = None
            self._ready.set()
            await asyncio.sleep(1)

    async def _session(self):
        async with websockets.connect(self.url, max_size=None, ping_interval=None) as ws:
            self._ws = ws
            self.connected = True
            self._ready.set()
            logger.info("jxemu: conectado al firmware")
            await ws.send(bytes([PROVIDE_DISPLAY]))
            pending = b""
            frame_bytes = DISPLAY_SIZE[0] * DISPLAY_SIZE[1] * 2
            async for message in ws:
                if not message:
                    continue
                command, body = message[0], message[1:]
                if command == PROVIDE_DISPLAY:
                    pending += body
                    if len(pending) >= frame_bytes:
                        self.framebuffer.put(_rgb565_to_image(pending[:frame_bytes]))
                        pending = b""
                elif command == 1:
                    self.camera_on = True
                    await self._send_camera_frame()
                elif command == 2:
                    self.camera_on = False
