# Firmware de Passport 2 (Gen 1.2, pantalla color) compilado como binario nativo, mas el
# shim pxemu que le pone carcasa web. Umbrel no permite `build:` en los compose: la imagen
# tiene que venir hecha y multi-arch. El Rust de `extmod/foundation-rust` compila contra el
# host, asi que cada arquitectura se construye en su runner nativo (ver images.yml).
ARG PASSPORT_TAG=v2.3.11

FROM python:3.11-slim-bookworm AS builder
ARG PASSPORT_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential automake autoconf libtool pkg-config libffi-dev \
        git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# 1.77.1 es la version con la que compila `extmod/foundation-rust`; cbindgen le genera los
# headers que despues incluye el C. Perfil minimal: no hacen falta ni docs ni clippy.
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.77.1 --profile minimal \
    && /root/.cargo/bin/cargo install cbindgen --version 0.26.0 --locked
ENV PATH=/root/.cargo/bin:$PATH

# passport2 no tiene submodulos: trezor-firmware y foundation-rust estan vendorizados.
RUN git clone --depth 1 --branch "${PASSPORT_TAG}" \
        https://github.com/Foundation-Devices/passport2.git /src

# Sin este parche el dispositivo se congela al poner el PIN y no vuelve a arrancar:
# el porque esta en patches/LEEME.md. Si upstream toca el archivo, el apply falla y frena
# el build, que es la senal que se busca.
COPY patches/ /patches/
RUN cd /src && git apply --verbose /patches/*.patch

# `make color` = Gen 1.2. La mono (Gen 1) ya no se fabrica y no se empaqueta.
RUN cd /src/simulator && make color

# El binario sale con simbolos de debug (13 MB). Y de todo el arbol clonado solo sobreviven
# las cuatro rutas que el firmware necesita en runtime: el binario, `simulator/` (sim_boot y
# sim_modules), los modulos de Passport y `uasyncio`, el unico paquete importable de extmod.
RUN strip /src/ports/unix/passport-mpy \
    && mkdir -p /out/simulator /out/extmod \
    && cp /src/ports/unix/passport-mpy /out/passport-mpy \
    && cp /src/simulator/sim_boot.py /out/simulator/ \
    && cp -r /src/simulator/sim_modules /out/simulator/sim_modules \
    && cp -r /src/ports/stm32/boards/Passport/modules /out/modules \
    && cp -r /src/extmod/uasyncio /out/extmod/uasyncio \
    && find /out -name '__pycache__' -prune -exec rm -rf {} +

# El encoder/decoder de UR de Foundation: los QR animados de PSBT entran y salen por ahi.
# No esta en PyPI (el paquete `ur` de PyPI es otra cosa, sin relacion).
RUN git clone --depth 1 https://github.com/Foundation-Devices/foundation-ur-py.git /ur-py


FROM python:3.11-slim-bookworm

# pillow/numpy: la pantalla RGB565 y los frames de la camara. qrcode + mnemonic + urtypes:
# los QR que "ve" la camara (SeedQR numerico y UR animado).
RUN pip install --no-cache-dir pillow numpy qrcode mnemonic urtypes

COPY --from=builder /out /app
COPY --from=builder /ur-py/ur /usr/local/lib/python3.11/site-packages/ur
COPY pxemu /app/pxemu
COPY help /app/help
COPY start.py /app/start.py

ENV PYTHONUNBUFFERED=1 \
    PASSPORT_DATA_DIR=/data \
    PASSPORT_WEB_PORT=6080

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 px && useradd -m -u 1000 -g 1000 -s /bin/bash px \
    && mkdir -p /data/work/microsd && chown -R 1000:1000 /data /app

USER 1000:1000
WORKDIR /data
EXPOSE 6080
CMD ["python3", "/app/start.py"]
