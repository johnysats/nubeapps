# Firmware de Krux (upstream, sin parches) + el shim kxemu que lo corre headless.
# Umbrel no permite `build:` en los compose: la imagen tiene que venir hecha y multi-arch.
# Lo unico nativo es el modulo uUR (un .c chico), asi que buildx con QEMU alcanza.
ARG KRUX_TAG=v26.08.0

FROM python:3.12-slim-bookworm AS builder
ARG KRUX_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${KRUX_TAG}" https://github.com/selfcustody/krux.git /krux

WORKDIR /krux
# embit es un submodulo y se instala como paquete.
# uUR es el modulo BC-UR nativo (los mismos fuentes cUR que corren en el dispositivo): se
# instala desde su repo, pinneado por MaixPy, para no clonar MaixPy entero. De MaixPy solo
# hacen falta los board.py de cada dispositivo (el mock de `board` los lee), no las 2 GB
# del arbol de MicroPython: se clona en modo sparse el commit que el tag de krux pinnea.
RUN git submodule update --init --depth 1 vendor/embit \
    && MAIXPY_SHA=$(git ls-tree HEAD firmware/MaixPy | awk '{print $3}') \
    && rm -rf firmware/MaixPy \
    && git clone --filter=blob:none --sparse --no-checkout \
        https://github.com/selfcustody/MaixPy.git firmware/MaixPy \
    && cd firmware/MaixPy \
    && git sparse-checkout set --no-cone "projects/*/builtin_py" \
    && git fetch --depth 1 origin "${MAIXPY_SHA}" \
    && git checkout --detach FETCH_HEAD \
    && git ls-tree HEAD components/micropython/port/src/bc-ur | awk '{print $3}' > /tmp/cur_sha

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        numpy \
        opencv-python-headless \
        Pillow \
        pygame \
        pyzbar \
        pycryptodome \
        qrcode \
        PyQRCode \
        "uUR @ git+https://github.com/selfcustody/cUR@$(cat /tmp/cur_sha)" \
        /krux/vendor/embit

# Se queda solo lo que el simulador ejecuta: firmware (src), los mocks y las carcasas
# (simulator), las fuentes .bdf y los board.py de MaixPy.
RUN rm -rf /krux/docs /krux/tests /krux/i18n /krux/vendor /krux/firmware/Kboot \
        /krux/simulator/sequences /krux/overrides \
    && find /krux -name .git -prune -exec rm -rf {} + \
    && find /krux -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /krux/firmware -mindepth 1 -maxdepth 1 ! -name font ! -name MaixPy -exec rm -rf {} + \
    # 21 de los 25 MB del checkout son fuentes .bdf, y cada dispositivo usa dos. Se quedan
    # las del Amigo (KXEMU_DEVICE): unifont-16 y FusionPixel-14, que son de los modelos a
    # botones, sumaban 13 MB. Si algun dia se empaqueta otro modelo, hay que traerlas.
    && find /krux/firmware/font -name '*.bdf' \
        ! -name 'ter-u24b.bdf' ! -name 'NotoSansCJK-24.bdf' -delete \
    # pip no hace falta en runtime
    && rm -rf /opt/venv/lib/python3.12/site-packages/pip \
        /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
    && find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} +


FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive

# zbar: decodifica los QR que "ve" la camara virtual. SDL no se instala: la rueda de pygame
# ya trae sus propias libSDL2 en pygame.libs, y pygame dibuja la pantalla del K210 en una
# superficie en memoria (sin ventana, SDL_VIDEODRIVER=dummy).
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /krux /krux
COPY kxemu /app/kxemu
COPY help /app/help
COPY start.py /app/start.py

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy \
    KXEMU_KRUX_DIR=/krux \
    KXEMU_DATA_DIR=/data \
    KXEMU_SD_DIR=/data/sd \
    KXEMU_DEVICE=maixpy_amigo \
    KXEMU_PORT=6080

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 krux && useradd -m -u 1000 -g 1000 -s /bin/bash krux \
    && mkdir -p /data/sd /data/flash && chown -R 1000:1000 /data /krux /app

USER 1000:1000
WORKDIR /app
EXPOSE 6080
CMD ["python3", "/app/start.py"]
