"""Display virtual: en vez de escribir a un ST7789 por SPI, publica el frame.

`BaseDisplayDriver` solo exige `show_image()` y `_width`/`_height`, asi que alcanza con
una subclase y un monkeypatch del factory. El Renderer de upstream no se toca.
"""
import threading
import time

from PIL import Image

# El ST7789 real tarda ~50 ms en volcar un frame 240x240 por SPI, y ese tiempo es lo
# unico que limita los loops de render de upstream (p.ej. el screensaver, que gira sin
# sleep). El display virtual escribe a memoria y retorna instantaneo, asi que sin este
# throttle esos loops queman un core entero.
MIN_FRAME_INTERVAL = 0.05


class FrameBuffer:
    """Ultimo frame de la pantalla + numero de secuencia para el stream MJPEG."""

    def __init__(self, width=240, height=240):
        self._cond = threading.Condition()
        self._image = Image.new("RGB", (width, height), "black")
        self._seq = 0

    def put(self, image: Image.Image):
        with self._cond:
            self._image = image.convert("RGB")
            self._seq += 1
            self._cond.notify_all()

    def current(self):
        with self._cond:
            return self._seq, self._image

    def wait_for_next(self, last_seq, timeout=5.0):
        """Devuelve (seq, image); si no hubo cambios en `timeout` repite el actual."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self._image


framebuffer = FrameBuffer()


def install():
    from seedsigner.hardware.displays import display_driver

    class VirtualDisplay(display_driver.BaseDisplayDriver):
        _last_frame_at = 0.0

        def show_image(self, image, x_start: int = 0, y_start: int = 0):
            remaining = MIN_FRAME_INTERVAL - (time.monotonic() - VirtualDisplay._last_frame_at)
            if remaining > 0:
                time.sleep(remaining)
            VirtualDisplay._last_frame_at = time.monotonic()

            if x_start or y_start or image.size != (self.width, self.height):
                # Refresco parcial: componer sobre lo que ya habia en pantalla.
                _, current = framebuffer.current()
                canvas = current.copy()
                canvas.paste(image.convert("RGB"), (x_start, y_start))
                image = canvas
            framebuffer.put(image)

    def instantiate_display_driver(cls, display_type=display_driver.DISPLAY_TYPE__ST7789,
                                   width: int = None, height: int = None):
        return VirtualDisplay(_width=width or 240, _height=height or 240)

    display_driver.DisplayDriverFactory.instantiate_display_driver = classmethod(
        instantiate_display_driver
    )
