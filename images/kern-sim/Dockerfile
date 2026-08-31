# Simulador de escritorio de Kern (upstream, sin parches) + el shim kxsim que lo sirve por web.
# Umbrel no permite `build:` en los compose: la imagen tiene que venir hecha y multi-arch.
# El simulador es C y compila en ~1 min, asi que se construye nativo en cada arquitectura.
ARG KERN_TAG=0.0.18

FROM debian:bookworm-slim AS builder
ARG KERN_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates pkg-config \
        libsdl2-dev libmbedtls-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${KERN_TAG}" --recursive --shallow-submodules \
        https://github.com/odudex/Kern.git /src

# La camara: se compila con SIM_WEBCAM=ON, pero el driver V4L2 de upstream se reemplaza por
# el nuestro. Ver el comentario de kxsim/v4l2_capture.c: el `--qr-dir` carga una sola imagen
# por sesion de camara (no alcanza para un QR animado) y el camino del webcam es el unico que
# pide un frame nuevo en cada vuelta. No hay /dev/video0 en el contenedor.
COPY kxsim/v4l2_capture.c /src/simulator/platform/video_sim/v4l2_capture.c

# upstream solo prueba el build Debug, donde glibc no marca fread() como warn_unused_result;
# con -O2 ese -Werror frena el build en efuse_hmac_sim.c. Debug no es opcion: el login hace
# PBKDF2 de 100.000 iteraciones y sin optimizar son varios segundos por PIN.
RUN sed -i '/-Werror=unused-result/d' /src/simulator/CMakeLists.txt

WORKDIR /src/simulator
# -flax-vector-conversions: en aarch64 libwally toma el smix de NEON porque __ARM_NEON esta
# definido, pero ese archivo esta escrito para el NEON de 32 bits. Es el mismo flag que le
# pone el configure de libwally.
RUN cmake -B build -S . \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS=-flax-vector-conversions \
        -DSIM_WEBCAM=ON \
        -DSIM_BOARD=wave_4b -DSIM_LCD_H_RES=720 -DSIM_LCD_V_RES=720 \
    && cmake --build build -- -j"$(nproc)" \
    && strip build/kern_simulator


FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb + xdotool: el simulador dibuja con SDL en una ventana X. A diferencia de krux y
# seedsigner (donde la pantalla ya era una imagen en memoria de Python), aca el firmware es
# un binario nativo: la pantalla se captura del framebuffer X y el tactil entra como mouse.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsdl2-2.0-0 libmbedcrypto7 xvfb xdotool x11-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir Pillow qrcode

COPY --from=builder /src/simulator/build/kern_simulator /usr/local/bin/kern_simulator
COPY kxsim /app/kxsim
COPY help /app/help
COPY start.py /app/start.py

ENV PYTHONUNBUFFERED=1 \
    KXSIM_DATA_DIR=/data \
    KXSIM_SD_DIR=/data/sdcard \
    KXSIM_RUN_DIR=/run/kxsim \
    KXSIM_DISPLAY=:99 \
    KXSIM_PORT=6080

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 kern && useradd -m -u 1000 -g 1000 -s /bin/bash kern \
    && mkdir -p /data /run/kxsim && chown -R 1000:1000 /data /run/kxsim /app

USER 1000:1000
WORKDIR /app
EXPOSE 6080
CMD ["python3", "/app/start.py"]
