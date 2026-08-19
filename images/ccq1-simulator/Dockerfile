# Simulador Coldcard Q1 con el firmware ya compilado en la imagen.
# Umbrel no permite `build:` en los paquetes: la imagen tiene que venir hecha y multi-arch.
ARG FIRMWARE_TAG=2026-07-31T1605-v6.6.0QX

FROM debian:bookworm-slim AS builder
ARG FIRMWARE_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git pkg-config ca-certificates \
        autoconf automake libtool \
        libffi-dev libsdl2-dev libusb-1.0-0 \
        python3 python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Solo los submodulos de external/: los de stm32/ y misc/gpu/ (y los anidados de libngu, que
# son HALs de STM32) no los usa el simulador unix y pesan cientos de MB.
RUN git clone --depth 1 --branch "${FIRMWARE_TAG}" \
        https://github.com/Coldcard/firmware.git /sim/firmware \
    && cd /sim/firmware \
    && git submodule update --init --filter=blob:none \
        external/micropython external/libngu external/mpy-qr external/ckcc-protocol

WORKDIR /sim/firmware/unix

# Equivale a "make setup" menos el target 'tools' (micropython vanilla, que el simulador no
# usa y cuyo libffi from-source rompe el build).
RUN ln -sfn ../external/micropython/ports/unix l-port \
    && ln -sfn ../external/micropython l-mpy \
    && ln -sfn ../external/micropython/ports/unix/coldcard-mpy coldcard-mpy \
    && (cd ../external/micropython/ports/unix && git submodule update --init --filter=blob:none) \
    && make ngu-setup \
    && make -C ../external/micropython/mpy-cross -j"$(nproc)" \
    && make \
    # En runtime el simulador solo usa unix/ (con el binario) y shared/ (MICROPYPATH);
    # el resto son fuentes y objetos de build (743MB -> ~15MB). shared/ tiene symlinks a
    # graphics/, misc/, stm32/ y external/ckcc-protocol: hay que resolverlos antes de borrar.
    && cp --remove-destination "$(readlink -f coldcard-mpy)" coldcard-mpy \
    && rm -f l-port l-mpy \
    && cd /sim/firmware \
    && find shared -type l -exec sh -c 'cp --remove-destination "$(readlink -f "$1")" "$1"' _ {} \; \
    && rm -rf external stm32 misc graphics testing hardware docs releases \
    && find /sim/firmware -name .git -prune -exec rm -rf {} +


FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates python3 python3-venv \
        libsdl2-2.0-0 libusb-1.0-0 \
        xvfb x11vnc x11-utils novnc websockify \
        # simulator.py corre el firmware dentro de un xterm (REPL); lo abre en +650+40,
        # fuera del framebuffer de 518x853, asi que no se ve en el navegador
        xterm xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# venv propio: bookworm marca el python del sistema como externally-managed
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
        PySDL2 Pillow numpy namedlist pyusb "ckcc-protocol[cli]"
ENV PATH=/opt/venv/bin:$PATH

# el paquete novnc no trae index.html: sin esto la raiz lista el directorio
COPY index.html /usr/share/novnc/index.html
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

COPY --from=builder /sim/firmware /sim/firmware

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 sim && useradd -m -u 1000 -g 1000 -s /bin/bash sim \
    && chown -R 1000:1000 /sim

USER 1000:1000
WORKDIR /sim/firmware/unix
EXPOSE 6080
CMD ["/usr/local/bin/start.sh"]
