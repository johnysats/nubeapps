"""El proceso del simulador: arrancarlo, reiniciarlo y el reset de fabrica.

El firmware no se apaga solo (`esp_restart()` en el simulador de upstream es un `exit(1)`),
asi que el supervisor lo relanza: para el usuario es el boton de encendido del dispositivo.
"""
import os
import shutil
import signal
import subprocess
import threading
import time

BINARY = "/usr/local/bin/kern_simulator"
DATA_DIR = os.environ.get("KXSIM_DATA_DIR", "/data")
DISPLAY = os.environ.get("KXSIM_DISPLAY", ":99")
# Lo que borra un reset de fabrica: la NVS (settings, PIN, contador de intentos) y la SPIFFS
# (mnemonics y descriptores guardados en la "flash" del dispositivo). La MicroSD no se toca:
# son los archivos del usuario y los ve por /files.
STATE_DIRS = ("nvs", "spiffs")


class Device:
    def __init__(self, camera_path):
        self.camera_path = camera_path
        self._process = None
        self._lock = threading.Lock()

    def start(self):
        # KXSIM_VERBOSE=1 sube el firmware a DEBUG: sirve para ver por que rechazo un QR.
        verbose = ["--verbose"] if os.environ.get("KXSIM_VERBOSE") == "1" else []
        with self._lock:
            self._process = subprocess.Popen(
                [
                    BINARY,
                    *verbose,
                    "--data-dir",
                    DATA_DIR,
                    # El "webcam" es el archivo de frames que publica kxsim/camera.py.
                    # Va pegado con "=": upstream lo declara como optional_argument y
                    # getopt_long descarta el valor si viene separado por un espacio.
                    f"--webcam={self.camera_path}",
                ],
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
        """Borra el estado interno y rearranca: el dispositivo vuelve a estrenar."""
        self.stop()
        for name in STATE_DIRS:
            shutil.rmtree(os.path.join(DATA_DIR, name), ignore_errors=True)
        self.start()

    def watch(self):
        """Relanza el firmware si termina solo (esp_restart() del simulador es un exit)."""
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
            print(f"kxsim: el firmware termino con codigo {code}, rearrancando")
            self.start()


device = None


def start(camera_path):
    global device
    device = Device(camera_path)
    device.start()
    threading.Thread(target=device.watch, daemon=True).start()
    return device
