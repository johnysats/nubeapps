"""El proceso del simulador: arrancarlo, reiniciarlo y el reset de fabrica."""
import os
import shutil
import signal
import subprocess
import threading
import time

BINARY = "/usr/local/bin/keystone3-simulator"
# El firmware resuelve la unidad "C:" de LVGL como ./ui_simulator relativo al cwd, y ahi
# adentro esta el symlink assets -> /data/assets.
HOME = os.environ.get("KSEMU_HOME", "/app/sim")
ASSETS_DIR = os.environ.get("KSEMU_ASSETS_DIR", "/data/assets")
DISPLAY = os.environ.get("KSEMU_DISPLAY", ":99")
# Lo que el reset de fabrica NO borra: la MicroSD son los archivos del usuario (los ve por
# /files) y el archivo de la camara lo reescribe el shim. Todo el resto de assets/ es la
# flash simulada del dispositivo: PIN, seed cifrada, ajustes y cuentas.
KEEP = ("sd", "qrcode_data.txt")


class Device:
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._process = subprocess.Popen(
                [BINARY],
                cwd=HOME,
                # SDL_RENDER_DRIVER=software: con el renderer acelerado SDL dibuja por OpenGL
                # y la ventana X queda con zonas negras al capturarla. Mismo flag que kern.
                env={**os.environ, "DISPLAY": DISPLAY, "SDL_VIDEODRIVER": "x11",
                     "SDL_RENDER_DRIVER": "software"},
            )
        return self._process

    def stop(self):
        with self._lock:
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def restart(self):
        self.stop()
        self.start()

    def factory_reset(self):
        """Borra la flash simulada y rearranca: el dispositivo vuelve a estrenar."""
        self.stop()
        for name in os.listdir(ASSETS_DIR):
            if name in KEEP:
                continue
            path = os.path.join(ASSETS_DIR, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except OSError as error:
                    print("ksemu: no pude borrar", name, error)
        self.start()

    def watch(self):
        """Relanza el firmware si termina solo.

        El menu del dispositivo tiene un apagado y un reinicio, y los dos terminan el
        proceso. Sin esto la app quedaria con la pantalla congelada hasta reinstalarla.
        """
        while True:
            with self._lock:
                process = self._process
            if process is None:
                time.sleep(0.5)
                continue
            code = process.wait()
            with self._lock:
                # Si lo paramos nosotros (reset, reinicio), start() ya puso el nuevo.
                if self._process is not process:
                    continue
            print(f"ksemu: el firmware termino con codigo {code}, rearrancando")
            self.start()


device = None


def start():
    global device
    device = Device()
    device.start()
    threading.Thread(target=device.watch, daemon=True).start()
    return device
