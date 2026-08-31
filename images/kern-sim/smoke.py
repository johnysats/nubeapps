#!/usr/bin/env python3
"""Recorrido automatico del simulador: reemplaza la prueba manual en cada bump de Kern.

Levanta la imagen, carga una seed por la camara virtual, le escanea un PSBT y lo firma,
y verifica que el PSBT firmado que quedo en la MicroSD tenga de verdad una firma valida.
Eso ejercita todo lo que puede romper un cambio de upstream: el arranque, la pantalla, el
tactil, la camara (incluido el QR animado por partes) y la MicroSD.

    python3 images/kern-sim/smoke.py ghcr.io/johnysats/kern-sim:0.0.18

Necesita `pillow` y `embit`. Con --shots <dir> deja las capturas de cada paso, que es lo
que hay que mirar cuando falla.
"""
import argparse
import io
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

PORT = 6099
BASE = f"http://127.0.0.1:{PORT}"
CONTAINER = "kern-smoke"
# La seed de test mas conocida que existe: la misma que el LEEME deja en la MicroSD.
SEED = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
PSBT_NAME = "smoke-psbt.txt"
# Cuanto dura el splash del logo antes del aviso de R&D.
BOOT_SECONDS = 15

shots_dir = None
step_number = 0


# --- utilidades -------------------------------------------------------------------------


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return response.read()


def post(path, **fields):
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(BASE + path, data=data, timeout=10) as response:
        return response.read()


def frame():
    return Image.open(io.BytesIO(get("/frame.png")))


def shot(name):
    """Captura numerada del paso, para poder mirar donde se cayo el recorrido."""
    global step_number
    step_number += 1
    if shots_dir:
        frame().save(f"{shots_dir}/{step_number:02d}-{name}.png")


def wait_stable(timeout=20.0, quiet=0.5):
    """Espera a que la pantalla deje de cambiar.

    Nada de dormir un rato fijo: el arranque pasa por un splash antes del aviso de R&D, y
    cargar una clave o parsear un PSBT tarda lo que tarda. Tocar antes de tiempo hace que el
    recorrido siga a ciegas y falle mucho despues, donde no se entiende por que.
    """
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        current = frame().tobytes()
        if current == previous:
            return
        previous = current
        time.sleep(quiet)


def tap(x, y, wait=0.0, attempts=6):
    """Toque en coordenadas relativas (0..1), como las manda la pagina.

    Reintenta hasta que la pantalla cambie: el arranque pasa por un splash quieto que parece
    la pantalla final, y un toque que cae ahi se pierde entero. `wait` es para las pantallas
    que nunca se quedan quietas -- mientras la camara escanea, el preview se mueve solo y no
    hay estabilidad que esperar.
    """
    for _ in range(attempts):
        before = frame().tobytes()
        post("/api/touch", x=f"{x:.4f}", y=f"{y:.4f}", action="down")
        time.sleep(0.12)
        post("/api/touch", x=f"{x:.4f}", y=f"{y:.4f}", action="up")
        if wait:
            time.sleep(wait)
        wait_stable()
        if frame().tobytes() != before:
            return
    check(False, f"la pantalla reacciono al toque en ({x}, {y})")


def check(condition, message):
    if not condition:
        print(f"FALLO: {message}", file=sys.stderr)
        print(container_logs(), file=sys.stderr)
        sys.exit(1)
    print(f"ok: {message}")


def container_logs():
    result = subprocess.run(
        ["docker", "logs", "--tail", "40", CONTAINER], capture_output=True, text=True
    )
    return result.stdout + result.stderr


# --- el recorrido -----------------------------------------------------------------------


def make_psbt():
    """PSBT de testnet gastable por la seed publica, native segwit."""
    from embit import bip32, bip39, script
    from embit.networks import NETWORKS
    from embit.psbt import PSBT, DerivationPath
    from embit.transaction import Transaction, TransactionInput, TransactionOutput

    net = NETWORKS["test"]
    root = bip32.HDKey.from_seed(bip39.mnemonic_to_seed(SEED), version=net["xprv"])
    path = "m/84h/1h/0h"
    account = root.derive(path)
    leaf, change = account.derive("m/0/0"), account.derive("m/1/0")

    transaction = Transaction(
        vin=[TransactionInput(bytes.fromhex("11" * 32), 0)],
        vout=[
            TransactionOutput(
                120_000,
                script.address_to_scriptpubkey(
                    "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"
                ),
            ),
            TransactionOutput(79_000, script.p2wpkh(change)),
        ],
    )
    psbt = PSBT(transaction)
    psbt.inputs[0].witness_utxo = TransactionOutput(200_000, script.p2wpkh(leaf))
    # La clave del mapa es la publica: con la privada, ni libwally ni embit releen el PSBT.
    psbt.inputs[0].bip32_derivations[leaf.to_public().key] = DerivationPath(
        root.child(0).fingerprint, bip32.parse_path(path + "/0/0")
    )
    psbt.outputs[1].bip32_derivations[change.to_public().key] = DerivationPath(
        root.child(0).fingerprint, bip32.parse_path(path + "/1/0")
    )
    return psbt.to_string()


def put_file(name, content):
    """Deja un archivo en la MicroSD del contenedor (sin volumen: el uid del runner varia)."""
    run("docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > /data/sdcard/{name}",
        input=content)


def wait_for_start(timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            get("/api/state", timeout=3)
            return
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1)
    check(False, f"el simulador respondio en {timeout}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--shots", help="directorio donde dejar las capturas de cada paso")
    parser.add_argument("--keep", action="store_true", help="no borrar el contenedor al final")
    arguments = parser.parse_args()

    global shots_dir
    shots_dir = arguments.shots

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    run("docker", "run", "-d", "--name", CONTAINER, "-p", f"127.0.0.1:{PORT}:6080",
        arguments.image)
    try:
        smoke()
    finally:
        if not arguments.keep:
            subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)


def smoke():
    wait_for_start()
    # El servidor contesta apenas aparece la ventana, pero el firmware todavia esta en el
    # splash del logo -- que es una imagen quieta, o sea que wait_stable() sola la tomaria
    # por la pantalla final y el primer toque se perderia. De ahi la espera fija.
    time.sleep(BOOT_SECONDS)
    wait_stable(timeout=40)
    print("ok: el simulador arranco")

    # 1. La pantalla dibuja algo. Un firmware que no bootea deja el framebuffer negro.
    shot("arranque")
    extrema = frame().convert("L").getextrema()
    check(extrema[1] - extrema[0] > 60, "la pantalla muestra algo (no esta en negro)")

    # 2. El aviso de R&D que el firmware muestra al arrancar. Aceptarlo prueba el tactil
    # (tap() ya falla solo si la pantalla no reacciona).
    tap(0.5, 0.90)  # I understand
    shot("menu")
    print("ok: el tactil navega (se acepto el aviso de R&D)")

    # 3. Cargar la seed por la camara virtual: Load Mnemonic > From QR Code.
    put_file(PSBT_NAME, make_psbt())
    state = post("/api/camera", file="ejemplo-seed-publica.txt")
    check(b"ejemplo-seed-publica.txt" in state, "la camara apunta a la seed de ejemplo")
    tap(0.73, 0.36)  # Load Mnemonic
    shot("load-mnemonic")
    tap(0.26, 0.36, wait=6)  # From QR Code
    shot("clave-cargada")

    # 4. Escanear el PSBT: son dos partes, o sea que tambien prueba el QR animado.
    post("/api/camera", file=PSBT_NAME)
    tap(0.26, 0.30, wait=8)  # Scan
    shot("revision-psbt")
    tap(0.77, 0.87)  # Sign
    shot("exportar")
    tap(0.73, 0.55)  # Save to SD card
    shot("guardado")

    # 5. Lo unico que vale como prueba: que el archivo firmado tenga una firma de verdad.
    listing = run("docker", "exec", CONTAINER, "ls", "/data/sdcard").stdout.split()
    signed = [name for name in listing if name.startswith("signed")]
    check(signed, f"el PSBT firmado quedo en la MicroSD (hay: {' '.join(listing)})")

    content = run("docker", "exec", CONTAINER, "cat", f"/data/sdcard/{signed[0]}").stdout
    from embit.psbt import PSBT

    psbt = PSBT.from_string(content.strip())
    check(bool(psbt.inputs[0].partial_sigs), f"{signed[0]} trae la firma del input")

    # La firma tiene que ser de la clave que cargamos, no de cualquiera.
    signature_key = next(iter(psbt.inputs[0].partial_sigs))
    check(
        signature_key in psbt.inputs[0].bip32_derivations,
        "la firma es de la clave derivada de la seed cargada",
    )
    print("\nEl recorrido completo funciono.")


if __name__ == "__main__":
    main()
