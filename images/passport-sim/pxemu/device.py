"""El firmware corre como hijo, y todo el hardware entra y sale por cinco pipes.

`simulator/simulator.py` de upstream es una ventana SDL que habla con el binario
`passport-mpy` (MicroPython unix) por descriptores heredados. No hace falta ni X11 ni SDL
para eso: lo unico que hay que respetar es el protocolo de cada pipe.

| Pipe | Sentido | Que lleva |
|---|---|---|
| oled | firmware -> shim | la pantalla entera, 240x320 RGB565 little-endian, sin cabecera |
| numpad | shim -> firmware | una tecla por linea, `<tecla>:d` o `<tecla>:u` |
| led | firmware -> shim | un byte: mascara en el nibble alto, valores en el bajo |
| cam_cmd | firmware -> shim | `enable` / `disable` / `capture`, separados por saltos de linea |
| cam_img | shim -> firmware | la respuesta a `capture`: 396x330 RGB565 |
"""
import logging
import os
import subprocess
import threading
import time

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DISPLAY_SIZE = (240, 320)  # Gen 1.2 (pantalla color)
FRAME_BYTES = DISPLAY_SIZE[0] * DISPLAY_SIZE[1] * 2

# Las teclas tal cual las nombra `simulator.py`: el navpad, los dos botones laterales
# (x = atras, y = seleccionar) y el teclado numerico.
KEYS = set("0123456789*#xyudlr")

GENUINE_LED = 0x1


class FrameBuffer:
    """Ultimo frame + numero de secuencia, para el long-poll de /frame.png."""

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
    """RGB565 little-endian a RGB de 8 bits.

    El orden de los bytes esta a la vista en `render_color()` de upstream, que arma cada
    pixel con `buf[offset + 1]` como byte alto. Y los 5 o 6 bits de cada canal se estiran
    replicando los altos (31 -> 255), no con un shift, que dejaria la pantalla apagada.
    """
    width, height = DISPLAY_SIZE
    raw = np.frombuffer(buf, dtype="<u2").reshape(height, width)
    red5 = (raw >> 11) & 0x1F
    green6 = (raw >> 5) & 0x3F
    blue5 = raw & 0x1F
    red = (red5 << 3) | (red5 >> 2)
    green = (green6 << 2) | (green6 >> 4)
    blue = (blue5 << 3) | (blue5 >> 2)
    return Image.fromarray(np.dstack([red, green, blue]).astype("uint8"))


class Device:
    def __init__(self, binary, boot_script, module_path, work_dir, camera_source):
        self.binary = binary
        self.boot_script = boot_script
        self.module_path = module_path
        self.work_dir = work_dir
        self.camera = camera_source
        self.framebuffer = FrameBuffer(DISPLAY_SIZE)
        self.camera_on = False
        self.genuine_led = False
        self.process = None
        self._numpad = None
        self._cam_img = None
        self._pressed = set()
        self._lock = threading.Lock()

    def start(self):
        oled_r, oled_w = os.pipe()
        led_r, led_w = os.pipe()
        numpad_r, numpad_w = os.pipe()
        cam_cmd_r, cam_cmd_w = os.pipe()
        cam_img_r, cam_img_w = os.pipe()

        env = os.environ.copy()
        env["MICROPYPATH"] = ":" + ":".join(self.module_path)
        command = [
            self.binary,
            # El firmware simula la flash en RAM; 30m es lo que le pasa upstream.
            "-X", "heapsize=30m",
            "-i", self.boot_script,
            str(oled_w), str(numpad_r), str(led_w), str(cam_cmd_w), str(cam_img_r),
            "color",
        ]
        self.process = subprocess.Popen(
            command, env=env, cwd=self.work_dir,
            pass_fds=[oled_w, numpad_r, led_w, cam_cmd_w, cam_img_r],
        )
        for fd in (oled_w, numpad_r, led_w, cam_cmd_w, cam_img_r):
            os.close(fd)

        self._numpad = open(numpad_w, "wb", closefd=True, buffering=0)
        self._cam_img = open(cam_img_w, "wb", closefd=True, buffering=0)
        threading.Thread(target=self._read_display, args=(oled_r,), daemon=True).start()
        threading.Thread(target=self._read_camera_commands, args=(cam_cmd_r,), daemon=True).start()
        threading.Thread(target=self._read_leds, args=(led_r,), daemon=True).start()
        logger.info("pxemu: firmware arrancado (pid %s)", self.process.pid)

    def press(self, key, action="tap"):
        """Una tecla. `tap` es down + up; `down`/`up` los manda la pagina al arrastrar."""
        if key not in KEYS:
            return False
        if action == "tap":
            self._send(key, True)
            # 300 ms abajo, no un pulso corto: con 120 ms el firmware se comia uno de cada
            # dos taps. `keypad.py` filtra por tiempo lo que entra a su cola.
            threading.Timer(0.3, self._send, args=(key, False)).start()
        else:
            self._send(key, action == "down")
        return True

    def _send(self, key, is_down):
        with self._lock:
            # Upstream ignora un down repetido y un up sin down: el estado se lleva aca.
            if is_down == (key in self._pressed):
                return
            if is_down:
                self._pressed.add(key)
            else:
                self._pressed.discard(key)
            try:
                self._numpad.write(f"{key}:{'d' if is_down else 'u'}\n".encode())
            except OSError:
                pass

    def _read_display(self, fd):
        stream = open(fd, "rb", closefd=True, buffering=0)
        pending = bytearray()
        while True:
            chunk = stream.read(FRAME_BYTES)
            if not chunk:
                if self.process.poll() is not None:
                    return
                continue
            pending += chunk
            while len(pending) >= FRAME_BYTES:
                frame = bytes(pending[:FRAME_BYTES])
                del pending[:FRAME_BYTES]
                self.framebuffer.put(_rgb565_to_image(frame))

    def _read_camera_commands(self, fd):
        stream = open(fd, "rb", closefd=True, buffering=0)
        while True:
            chunk = stream.read(4096)
            if not chunk:
                if self.process.poll() is not None:
                    return
                continue
            for command in chunk.decode("utf-8", "replace").split("\n"):
                if command == "enable":
                    self.camera_on = True
                elif command == "disable":
                    self.camera_on = False
                elif command == "capture":
                    # Bloquea hasta que el firmware termine de leer el frame, que es
                    # justo lo que se quiere: pide de a uno y espera por el.
                    try:
                        self._cam_img.write(self.camera.next_frame())
                    except OSError:
                        return

    def _read_leds(self, fd):
        stream = open(fd, "rb", closefd=True, buffering=0)
        while True:
            chunk = stream.read(64)
            if not chunk:
                if self.process.poll() is not None:
                    return
                continue
            for byte in chunk:
                mask, values = (byte >> 4) & 0xF, byte & 0xF
                if mask & GENUINE_LED:
                    self.genuine_led = bool(values & GENUINE_LED)

    def wait(self):
        while self.process.poll() is None:
            time.sleep(1)
        return self.process.returncode
