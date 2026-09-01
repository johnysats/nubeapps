#!/bin/bash
# Escritorio virtual sin window manager + noVNC recortado a la ventana del simulador,
# para que en el navegador se vea solo el dispositivo.
set -u

export DISPLAY=:99
export HOME=/home/sim
# Tiene que entrar la ventana del sim (518x853 dibujada en +100+100 por SDL) y el xterm
# del REPL, que queda fuera del recorte.
SCREEN="${SCREEN:-640x1024x24}"
SIM_ARGS="${SIM_ARGS:---q1 -l}"

cd /sim/firmware/unix || exit 1

# LEEME + seed de ejemplo la primera vez: una MicroSD vacia no dice como se usa. Solo si no
# hay ningun archivo, asi que si el usuario ya guardo lo suyo (o borro el LEEME) no vuelve.
SD_DIR=work/MicroSD
QR_DIR="$SD_DIR/QR-Camara"
mkdir -p "$SD_DIR"
# QR-Camara la crea este script en cada arranque, asi que no cuenta para decidir si la
# MicroSD sigue vacia.
if [ -z "$(ls -A "$SD_DIR" 2>/dev/null | grep -v '^QR-Camara$')" ]; then
    cp /usr/local/share/ccq1-help/*.txt "$SD_DIR"/ || echo "!!! no pude dejar la ayuda en $SD_DIR"
fi

# Camara virtual: qrfeed.py le entrega al escaner del firmware lo que se suba a QR-Camara.
mkdir -p "$QR_DIR"
[ -e "$QR_DIR/LEEME.txt" ] || cp /usr/local/share/ccq1-help/camara/LEEME.txt "$QR_DIR"/ \
    || echo "!!! no pude dejar la ayuda en $QR_DIR"
python3 /usr/local/bin/qrfeed.py &

Xvfb :99 -screen 0 "$SCREEN" -nolisten tcp &
for _ in $(seq 30); do xdpyinfo -display :99 >/dev/null 2>&1 && break; sleep 0.5; done

# Si el simulador se cierra (Control-Q), se relanza: la pestana del browser sigue viva.
# eval: sin el, las comillas de SIM_ARGS quedan literales y --seed "a b c" se rompe.
(
    while true; do
        eval "./simulator.py $SIM_ARGS"
        echo ">>> simulador termino, relanzando en 3s..."
        sleep 3
    done
) &

# Geometria real de la ventana del simulador: x11vnc exporta solo eso (-clip), asi que el
# escritorio, el xterm del REPL y los bordes no llegan al navegador.
CLIP=""
for _ in $(seq 60); do
    CLIP=$(xwininfo -root -children 2>/dev/null \
        | grep '"Coldcard Simulator"' \
        | grep -oE '[0-9]+x[0-9]+\+[0-9]+\+[0-9]+' | head -1)
    [ -n "$CLIP" ] && break
    sleep 1
done
if [ -z "$CLIP" ]; then
    echo "!!! no aparecio la ventana del simulador; exporto el escritorio entero"
    CLIP_ARGS=()
else
    echo ">>> recortando VNC a $CLIP"
    CLIP_ARGS=(-clip "$CLIP")
fi

# -localhost: el puerto VNC crudo no queda expuesto a los demas contenedores de Umbrel.
x11vnc -display :99 -forever -shared -nopw -quiet -localhost -rfbport 5900 "${CLIP_ARGS[@]}" &
websockify --web=/usr/share/novnc 6080 localhost:5900 &

wait -n
