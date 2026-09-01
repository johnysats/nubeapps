# Simulador de escritorio de Keystone 3 Pro (upstream) + el shim ksemu que lo sirve por web.
# Umbrel no permite `build:` en los compose: la imagen tiene que venir hecha y multi-arch.
# El Rust de `rust/` compila contra el host, asi que se construye nativo en cada
# arquitectura y el indice se arma despues (igual que kern y passport).
ARG KEYSTONE_TAG=3.0.4

FROM debian:bookworm-slim AS builder
ARG KEYSTONE_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake make git curl ca-certificates pkg-config \
        python3 python3-pip libsdl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Las pide build.py para regenerar las imagenes a .c; el arbol ya las trae generadas, pero
# el script las importa igual antes de mirar si cambio algo.
RUN pip3 install --break-system-packages --no-cache-dir "PyYaml==6.0.1" "Pillow~=9.5.0"

RUN curl https://sh.rustup.rs -sSf | sh -s -- --default-toolchain none -y
ENV PATH=/root/.cargo/bin:$PATH

WORKDIR /src
# Sin --recursive: el submodulo `keystone3-firmware-release` es privado (404) y el clone
# entero se caeria. El unico que hace falta para el simulador es ctaes.
RUN git clone --depth 1 --branch "${KEYSTONE_TAG}" \
        https://github.com/KeystoneHQ/keystone3-firmware.git . \
    && git submodule update --init --depth 1 external/ctaes

# El toolchain va pinneado en el repo (rust-toolchain) y cambia entre releases.
RUN rustup toolchain install "$(cat rust-toolchain)" --profile minimal \
    && rustup default "$(cat rust-toolchain)" \
    && cargo install cbindgen

# --- Los tres parches, todos por la misma razon: sacar el lector de QR por captura de
# pantalla, que es el camino de macOS. Ver patches/LEEME.md.
COPY patches /patches
RUN sh /patches/aplicar.sh /src

RUN mkdir -p build && cd build \
    && cmake -G "Unix Makefiles" .. \
        -DLIB_RUST_C=ON -DBTC_ONLY=true -DBUILD_TYPE=Simulator \
        -DCMAKE_BUILD_TYPE=Debug -DRU_SUPPORT=true \
    && make -j"$(nproc)" \
    && strip simulator

# Las plantillas de las pantallas de transaccion, que upstream no incluye armadas.
COPY extraer-layouts.py /extraer-layouts.py
RUN python3 /extraer-layouts.py /src /layouts

# El encoder de UR que usa ksemu/camera.py; el runtime no trae git para bajarlo el mismo.
RUN git clone --depth 1 https://github.com/Foundation-Devices/foundation-ur-py.git /ur-py


FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb + xdotool: el simulador dibuja con SDL en una ventana X, igual que kern. La pantalla
# se captura del framebuffer y los toques entran como mouse, que es lo que LVGL trata como
# pantalla tactil.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsdl2-2.0-0 xvfb xdotool x11-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir Pillow

# El encoder de UR: el paquete que se llama `ur` en PyPI es otra cosa (una libreria de
# notebooks que arrastra Jupyter). Este es el de Foundation Devices, el mismo que usan
# jade-sim y passport-sim.
COPY --from=builder /ur-py/ur /usr/local/lib/python3.12/site-packages/ur

COPY --from=builder /layouts /app/layouts
COPY --from=builder /src/build/simulator /usr/local/bin/keystone3-simulator
COPY ksemu /app/ksemu
COPY help /app/help
COPY start.py /app/start.py

# El firmware resuelve la unidad "C:" de LVGL como ./ui_simulator relativo al cwd
# (lv_conf.h: LV_FS_STDIO_PATH), asi que corre desde /app/sim y todo su almacenamiento
# -la flash simulada, la MicroSD y el archivo de la camara- cae en el bind mount.
RUN mkdir -p /app/sim/ui_simulator /data/assets \
    && ln -s /data/assets /app/sim/ui_simulator/assets

ENV PYTHONUNBUFFERED=1 \
    KSEMU_HOME=/app/sim \
    KSEMU_ASSETS_DIR=/data/assets \
    KSEMU_SD_DIR=/data/assets/sd \
    KSEMU_DISPLAY=:99 \
    KSEMU_PORT=6080

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 keystone && useradd -m -u 1000 -g 1000 -s /bin/bash keystone \
    && mkdir -p /data/assets/sd && chown -R 1000:1000 /data /app

USER 1000:1000
WORKDIR /app
EXPOSE 6080
CMD ["python3", "/app/start.py"]
