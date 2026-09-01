#!/bin/sh
# Los cambios que necesita el simulador de upstream para correr headless en un contenedor.
# El porque de cada uno esta en LEEME.md. Van como sed y no como .patch a proposito: son
# cambios de una linea sobre archivos que upstream toca seguido, y un .patch fallaria por
# contexto en cada bump. Cada paso verifica que el patron estuviera: si upstream renombra
# algo, el build se cae aca con un mensaje claro en vez de compilar algo que no arranca.
set -e
SRC="$1"

fallar() {
    echo "ksemu: el parche '$1' no encontro lo que esperaba." >&2
    echo "  Lo mas probable es que upstream lo haya cambiado; ver images/keystone3-sim/patches/LEEME.md" >&2
    exit 1
}

# 1. La camara lee los QR del archivo assets/qrcode_data.txt en vez de capturar la pantalla.
grep -q '^#define GET_QR_DATA_FROM_SCREEN' "$SRC/ui_simulator/simulator_model.c" \
    || fallar "GET_QR_DATA_FROM_SCREEN"
sed -i 's|^#define GET_QR_DATA_FROM_SCREEN|// ksemu: la camara es el archivo, no la pantalla\n// &|' \
    "$SRC/ui_simulator/simulator_model.c"

# 2. y 3. Sacar el crate que capturaba la pantalla (ver LEEME.md: sus simbolos de dbus
# estaticos hacen segfaultear a SDL_Init).
grep -q '^simulator = \["dep:sim_qr_reader", ' "$SRC/rust/rust_c/Cargo.toml" \
    || fallar "dep:sim_qr_reader"
sed -i 's|^simulator = \["dep:sim_qr_reader", |simulator = [|' "$SRC/rust/rust_c/Cargo.toml"

# El `mod simulator;` viene con dos atributos arriba (#[cfg] y #[allow]) y un item que se
# borra deja los atributos colgados ("expected item after attributes"): se comentan los tres.
python3 - "$SRC/rust/rust_c/src/lib.rs" <<'PY'
import re
import sys

path = sys.argv[1]
source = open(path).read()
patched = re.sub(
    r'(?m)^(#\[cfg\(feature = "simulator"\)\]\n(?:#\[[^\n]*\]\n)*mod simulator;)',
    lambda match: "".join("// " + line + "\n" for line in match.group(1).splitlines()),
    source,
)
if patched == source:
    sys.exit("ksemu: el parche 'mod simulator' no encontro lo que esperaba.")
open(path, "w").write(patched)
PY
