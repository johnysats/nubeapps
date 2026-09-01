#!/usr/bin/env python3
"""Recorrido automatico del simulador: reemplaza la prueba manual en cada bump de Keystone.

Levanta la imagen, hace todo el alta (idioma, PIN, nombre), importa la seed publica tipeando
las 12 palabras, le escanea un PSBT por la camara virtual, lo firma y **lee el QR animado que
queda en la pantalla** para verificar que la firma es de la clave derivada de esa seed. Eso
ejercita lo que puede romper un cambio de upstream: el arranque, la pantalla, el tactil, la
camara, las plantillas de la pantalla de firmar y el QR de salida.

    python3 images/keystone3-sim/smoke.py ghcr.io/johnysats/keystone3-sim:3.0.4

Necesita `pillow`, `embit` y `zbarimg` (paquete zbar-tools). Con --shots <dir> deja las
capturas de cada paso, que es lo que hay que mirar cuando falla.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

PORT = 6099
BASE = f"http://127.0.0.1:{PORT}"
CONTAINER = "keystone3-smoke"
# La seed de test mas conocida que existe: la misma que el LEEME deja en la MicroSD.
SEED = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
PSBT_NAME = "smoke-psbt.txt"
# Cuanto dura el splash del logo antes de la pantalla de bienvenida.
BOOT_SECONDS = 12
# La pantalla del dispositivo. Las coordenadas de abajo van en pixeles de esta grilla, que
# es como estan anotadas en CLAUDE.md; la API toma relativas.
WIDTH, HEIGHT = 480, 800

# El teclado de la pantalla "Importa tu semilla". Solo hacen falta las letras que llevan a
# una unica sugerencia: "aban" -> abandon, "abou" -> about.
KEYS = {"a": (50, 697), "b": (286, 755), "n": (334, 755), "o": (406, 640), "u": (311, 640)}
SUGGESTION = (70, 583)

# Reensamblado del UR animado. Corre *dentro del contenedor*: la imagen ya trae la libreria
# `ur` (la de Foundation Devices, que no esta en PyPI) y asi el runner de CI solo necesita
# pillow, embit y zbarimg.
DECODE_UR = """
import sys
from ur.ur_decoder import URDecoder
from ur.cbor_lite import CBORDecoder

decoder = URDecoder()
for part in sys.stdin.read().split():
    decoder.receive_part(part)
    if decoder.is_complete():
        break
if not decoder.is_complete():
    sys.exit("faltan partes del UR")
psbt, _ = CBORDecoder(decoder.result_message().cbor).decodeBytes()
sys.stdout.write(psbt.hex())
"""

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


def wait_stable(timeout=20.0, quiet=0.4):
    """Espera a que la pantalla deje de cambiar.

    Nada de dormir un rato fijo: las transiciones de LVGL son animadas y cargar la seed o
    parsear el PSBT tarda lo que tarda. Tocar antes de tiempo hace que el recorrido siga a
    ciegas y falle mucho despues, donde no se entiende por que.
    """
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        current = frame().tobytes()
        if current == previous:
            return
        previous = current
        time.sleep(quiet)


def press(x, y, hold=0.15, settle=0.35):
    """Toque suelto en coordenadas de pantalla (pixeles), sin verificar nada.

    Es lo que se usa para el PIN y para las letras: son pantallas donde cada tecla cambia
    algo minimo y verificar tecla por tecla multiplicaria por cinco lo que tarda el
    recorrido. Un toque perdido igual se nota, porque el paso siguiente no aparece.
    """
    relative = {"x": f"{x / WIDTH:.4f}", "y": f"{y / HEIGHT:.4f}"}
    post("/api/touch", action="down", **relative)
    time.sleep(hold)
    post("/api/touch", action="up", **relative)
    time.sleep(settle)


def tap(x, y, wait=0.0, attempts=6):
    """Toque que se reintenta hasta que la pantalla reaccione.

    Es para los pasos de navegacion: si el dispositivo todavia estaba animando la pantalla
    anterior el toque se pierde entero, y seguir a ciegas desde ahi rompe todo lo que sigue.
    `wait` es para las pantallas que tardan en responder sin cambiar nada mientras tanto.
    """
    for _ in range(attempts):
        before = frame().tobytes()
        press(x, y)
        if wait:
            time.sleep(wait)
        wait_stable()
        if frame().tobytes() != before:
            return
    check(False, f"la pantalla reacciono al toque en ({x}, {y})")


def slide(y, start_x, end_x, steps=6):
    """Arrastre horizontal en coordenadas relativas, que es como lo manda la pagina."""
    post("/api/touch", x=f"{start_x:.4f}", y=f"{y:.4f}", action="down")
    for step in range(1, steps + 1):
        x = start_x + (end_x - start_x) * step / steps
        post("/api/touch", x=f"{x:.4f}", y=f"{y:.4f}", action="move")
        time.sleep(0.08)
    post("/api/touch", x=f"{end_x:.4f}", y=f"{y:.4f}", action="up")


def type_word(letters):
    """Una palabra de la seed: las letras a ciegas y la sugerencia verificada.

    Alcanza con el prefijo que deja una sola sugerencia. Si alguna letra se perdiera, la
    sugerencia seria otra palabra o no habria ninguna, y el recorrido se cae en el paso
    siguiente en vez de firmar con una seed equivocada.
    """
    for letter in letters:
        press(*KEYS[letter], settle=0.25)
    tap(*SUGGESTION)


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
    """PSBT gastable por la seed publica, native segwit. Mainnet: el firmware no hace testnet."""
    from embit import bip32, bip39, script
    from embit.networks import NETWORKS
    from embit.psbt import PSBT, DerivationPath
    from embit.transaction import Transaction, TransactionInput, TransactionOutput

    net = NETWORKS["main"]
    root = bip32.HDKey.from_seed(bip39.mnemonic_to_seed(SEED), version=net["xprv"])
    path = "m/84h/0h/0h"
    account = root.derive(path)
    leaf, change = account.derive("m/0/0"), account.derive("m/1/0")

    transaction = Transaction(
        vin=[TransactionInput(bytes.fromhex("11" * 32), 0)],
        vout=[
            TransactionOutput(
                120_000,
                script.address_to_scriptpubkey(
                    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
                ),
            ),
            TransactionOutput(79_000, script.p2wpkh(change)),
        ],
    )
    psbt = PSBT(transaction)
    psbt.inputs[0].witness_utxo = TransactionOutput(200_000, script.p2wpkh(leaf))
    fingerprint = root.child(0).fingerprint
    # La clave del mapa es la publica: con la privada, ni el firmware ni embit releen el PSBT.
    psbt.inputs[0].bip32_derivations[leaf.to_public().key] = DerivationPath(
        fingerprint, bip32.parse_path(path + "/0/0")
    )
    psbt.outputs[1].bip32_derivations[change.to_public().key] = DerivationPath(
        fingerprint, bip32.parse_path(path + "/1/0")
    )
    return psbt.to_string()


def put_file(name, content):
    """Deja un archivo en la MicroSD del contenedor (sin volumen: el uid del runner varia)."""
    run("docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > /data/assets/sd/{name}",
        input=content)


def read_animated_qr(timeout=60):
    """Las partes del UR que el dispositivo va mostrando, hasta poder reconstruirlo.

    El QR se busca en el frame entero, sin recortar: zbar lo encuentra igual y asi un cambio
    de layout de upstream no obliga a recalcular un recorte.
    """
    parts, deadline = set(), time.monotonic() + timeout
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "frame.png")
        while time.monotonic() < deadline:
            frame().convert("L").save(path)
            decoded = subprocess.run(
                ["zbarimg", "-q", "--raw", path], capture_output=True, text=True
            ).stdout.strip()
            if decoded:
                parts.add(decoded)
                signed = decode_ur(parts)
                if signed:
                    return signed
            time.sleep(0.15)
    check(False, f"se pudo leer el QR del PSBT firmado (partes leidas: {len(parts)}, "
          f"ultimo error: {getattr(decode_ur, 'last_error', 'ninguno')})")


def decode_ur(parts):
    """El PSBT en hexadecimal, o None si todavia faltan partes del UR."""
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python3", "-c", DECODE_UR],
        input="\n".join(parts), capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Que quede a mano el ultimo motivo: si el reensamblado falla por algo que no sea
        # "faltan partes", el recorrido se planta hasta el timeout sin decir por que.
        decode_ur.last_error = result.stderr.strip()
        return None
    return result.stdout.strip()


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

    # 2. Bienvenida e idioma. Se elige espanol, que es como se usa la app (y de paso prueba
    # que el firmware siga trayendo la traduccion, que es lo unico que lo distingue del
    # resto del store).
    tap(240, 655)  # flecha de la bienvenida
    shot("idioma")
    tap(433, 648)  # Espanol
    tap(395, 743)  # flecha
    shot("verificacion")
    print("ok: el tactil navega (se eligio el idioma)")

    # 3. Alta: saltear la verificacion y la actualizacion de firmware, importar billetera.
    tap(407, 96)  # Omitir (verifica tu dispositivo)
    tap(407, 96)  # Omitir (firmware)
    shot("nueva-billetera")
    tap(240, 750)  # Importar billetera
    tap(240, 743)  # Entiendo
    shot("pin")

    # 4. PIN 111111. El firmware avisa que es debil y hay que confirmarlo; despues lo repite.
    for _ in range(6):
        press(84, 532)
    wait_stable()
    shot("pin-debil")
    tap(112, 747)  # Continuar
    for _ in range(6):
        press(84, 532)
    wait_stable(timeout=30)
    shot("nombre")

    # 5. Nombre de la billetera: alcanza una letra.
    tap(380, 645)  # k
    tap(429, 767)  # flecha
    shot("metodo")
    tap(240, 460)  # Frase unica secreta
    tap(240, 554)  # 12 Palabras
    shot("importa-semilla")
    print("ok: el alta llego a la pantalla de importar la semilla")

    # 6. Las 12 palabras de la seed publica. La ultima completa la frase y el firmware entra
    # solo al home: si alguna palabra se hubiera perdido, el checksum no daria y no entraria.
    for _ in range(11):
        type_word("aban")
    type_word("abou")
    wait_stable(timeout=30)
    shot("home")
    print("ok: la seed se importo (el dispositivo entro al home)")

    # 7. Escanear el PSBT por la camara virtual.
    put_file(PSBT_NAME, make_psbt())
    state = json.loads(post("/api/camera", file=PSBT_NAME))
    check(state["parts"] >= 1 and not state["error"], "la camara armo el UR del PSBT")
    tap(240, 733, wait=3)  # ESCANEAR
    shot("confirmar")

    # La pantalla de firmar se arma con las plantillas JSON que instala el arranque: sin
    # ellas el titulo y el boton se ven igual, pero donde va el monto queda un hueco negro.
    amount = frame().convert("L").crop((50, 410, 440, 540)).getextrema()
    check(amount[1] > 150, "la pantalla de la transaccion muestra el monto")

    # 8. Firmar: el boton de abajo no es un boton, se arrastra de punta a punta.
    slide(0.93, 0.18, 0.98)
    wait_stable()
    shot("pin-firma")
    for _ in range(6):
        press(84, 532)
    wait_stable(timeout=30)
    shot("qr-firmado")

    # 9. Lo unico que vale como prueba: que el QR que muestra traiga una firma de verdad.
    from embit.psbt import PSBT

    signed = PSBT.parse(bytes.fromhex(read_animated_qr()))
    check(bool(signed.inputs[0].partial_sigs), "el QR de salida es un PSBT firmado")

    # Y que la firma sea de la clave que cargamos, no de cualquiera.
    signature_key = next(iter(signed.inputs[0].partial_sigs))
    check(
        signature_key in signed.inputs[0].bip32_derivations,
        "la firma es de la clave derivada de la seed cargada",
    )
    print("\nEl recorrido completo funciono.")


if __name__ == "__main__":
    main()
