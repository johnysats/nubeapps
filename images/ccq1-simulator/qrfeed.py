#!/usr/bin/env python3
# Camara virtual del Q1, por archivos.
#
# El escaner simulado del firmware (unix/variant/sim_scanner.py) no abre ninguna camara:
# mientras la pantalla de escaneo esta abierta hace polling de work/qrdata.txt y toma cada
# linea del archivo como un QR ya decodificado. Este watcher traduce "el usuario solto un
# archivo en la carpeta QR-Camara de la MicroSD" a ese archivo, asi el flujo por QR se hace
# desde /files igual que el de la MicroSD.
#
# Como el firmware recibe el contenido ya decodificado, no hay limite de tamano ni hace falta
# partirlo en BBQr: un PSBT entero entra en una sola "lectura".

import base64
import os
import sys
import time

WORK = os.environ.get("QRFEED_WORK", "/sim/firmware/unix/work")
WATCH_DIR = os.path.join(WORK, "MicroSD", "QR-Camara")
OUT = os.path.join(WORK, "qrdata.txt")   # nombre fijo, lo define sim_scanner.py
SKIP = {"LEEME.txt", "README.txt"}
POLL = 0.4


def log(msg):
    print(">>> qrfeed: %s" % msg, flush=True)


def newest():
    # (nombre, mtime, tamano) del archivo mas reciente de la carpeta, o None si esta vacia
    best = None
    try:
        names = os.listdir(WATCH_DIR)
    except OSError:
        return None
    for name in names:
        if name.startswith(".") or name in SKIP:
            continue
        path = os.path.join(WATCH_DIR, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if not os.path.isfile(path):
            continue
        key = (st.st_mtime, name, st.st_size)
        if best is None or key > best[0]:
            best = (key, path)
    return best


def to_lines(data):
    # Cada linea que escribimos es un QR leido. Casi siempre es una sola.
    if data[:5] == b"psbt\xff":
        return [base64.b64encode(data).decode()]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # binario que no es PSBT: el firmware igual reconoce base64 y hex
        return [base64.b64encode(data).decode()]

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    joined = "".join(lines)
    # Un PSBT en texto suele venir cortado en varias lineas: es un QR solo, no uno por linea.
    if joined.startswith("cHNidP") or joined[:10].lower() == "70736274ff":
        return [joined]
    return lines


def main():
    os.makedirs(WATCH_DIR, exist_ok=True)
    # Lo que ya estaba al arrancar no se escanea: solo lo que el usuario sube ahora.
    seen = newest()
    seen = seen[0] if seen else None
    try:
        last_mtime = int(os.stat(OUT).st_mtime)
    except OSError:
        last_mtime = 0

    log("mirando %s" % WATCH_DIR)
    while True:
        time.sleep(POLL)
        found = newest()
        if not found or found[0] == seen:
            continue
        seen, path = found

        try:
            with open(path, "rb") as fd:
                data = fd.read()
            lines = to_lines(data)
        except OSError as exc:
            log("no pude leer %s: %s" % (path, exc))
            continue
        if not lines:
            log("%s esta vacio, no hay nada que escanear" % os.path.basename(path))
            continue

        tmp = OUT + ".tmp"
        with open(tmp, "w") as fd:
            fd.write("\n".join(lines) + "\n")
        os.replace(tmp, OUT)
        # sim_scanner.py compara el mtime en segundos: si dos escaneos caen en el mismo
        # segundo el segundo se perderia, asi que forzamos que siempre crezca.
        last_mtime = max(int(time.time()), last_mtime + 1)
        os.utime(OUT, (last_mtime, last_mtime))

        log("%s -> %d QR (%d bytes)" % (os.path.basename(path), len(lines),
                                        sum(len(x) for x in lines)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
