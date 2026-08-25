# Simulador de Blockstream Jade Plus: el firmware de upstream corriendo en qemu-system-xtensa
# mas la carcasa web de jxemu.
#
# El firmware se compila una sola vez en el stage `fw` (la toolchain de esp-idf que publica
# Blockstream es solo amd64) y el binario resultante es neutro de arquitectura: la imagen
# final solo lleva ese binario y el qemu nativo de cada plataforma.
# La toolchain va atada al tag, no elegida por nosotros: cada release de Jade declara en su
# propio Dockerfile.qemu con que imagen se compila, y usar otra no es cosmetico -con la de
# master, el 1.0.40 ni linkea-. El workflow saca este digest del tag que se este empaquetando
# (`sed -n 's|^FROM blockstream/jade_builder@||p' Dockerfile.qemu`); el default de aca es el
# que le toca al JADE_VERSION de abajo, para los builds a mano.
ARG JADE_BUILDER=sha256:8b739db85b6b99664db0e3ece57cddfa4e0fee4101a20ca930c391273f21e2f9
FROM --platform=linux/amd64 blockstream/jade_builder@${JADE_BUILDER} AS fw

ARG JADE_VERSION=1.0.41
WORKDIR /jade
RUN git clone --depth 1 --branch "${JADE_VERSION}" --recursive \
        https://github.com/Blockstream/Jade.git /jade

# La config de qemu con pantalla grande (320x170, la del Jade Plus) espera una imagen de
# carcasa que upstream no tiene en el repo. La pagina que sirve el firmware no se usa aca
# -pide la webcam del navegador, que en HTTP no existe-, asi que alcanza con un PNG minimo
# para que el build no se caiga.
COPY jadel.png main/qemu/jadel.png

# El script de activacion del IDF 5.5 es de bash: con el /bin/sh por defecto (dash) falla
# con "Activation script failed" y despues no existe idf.py. Y export.sh solo encuentra el
# IDF si se lo ejecuta parado en su propio directorio, de ahi el cd.
# El armado de la imagen de flash se invoca por glob (make?flash?img.sh) y sin argumentos:
# el script cambio de nombre entre releases -make-flash-img.sh y make_flash_img.sh- y en las
# viejas no acepta parametros. Las dos versiones escriben en /flash_image.bin y /qemu_efuse.bin.
SHELL ["/bin/bash", "-c"]
RUN ./tools/switch_to.sh qemu --dev --psram --webdisplay-larger \
    && cd /opt/esp/idf && . ./export.sh && cd /jade \
    && idf.py all \
    && ./tools/fwprep.py build/jade.bin build \
    && ./main/qemu/make?flash?img.sh


FROM python:3.12-slim-bookworm

ARG TARGETARCH
ARG QEMU_RELEASE=esp-develop-9.2.2-20260417
ARG QEMU_BUILD=esp_develop_9.2.2_20260417

# libsdl2 y libslirp no son opcionales aunque qemu corra headless: el binario de Espressif
# las tiene enlazadas, y sin slirp no hay `-nic user` (que es como se llega al firmware).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils binutils \
        libglib2.0-0 libpixman-1-0 libslirp0 libgcrypt20 libsdl2-2.0-0 \
    && case "${TARGETARCH}" in \
         amd64) QEMU_ARCH=x86_64-linux-gnu ;; \
         arm64) QEMU_ARCH=aarch64-linux-gnu ;; \
         *) echo "arquitectura no soportada: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL -o /tmp/qemu.tar.xz \
        "https://github.com/espressif/qemu/releases/download/${QEMU_RELEASE}/qemu-xtensa-softmmu-${QEMU_BUILD}-${QEMU_ARCH}.tar.xz" \
    && mkdir -p /app && tar xf /tmp/qemu.tar.xz -C /app \
    # El binario de Espressif viene con los simbolos de debug: 72 MB que no le sirven a nadie
    # aca dentro. Stripeado son 17 MB y emula lo mismo.
    && strip --strip-unneeded /app/qemu/bin/qemu-system-xtensa \
    && rm /tmp/qemu.tar.xz \
    && apt-get purge -y curl xz-utils binutils && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El encoder de UR (los QR animados que lee Jade) no esta en PyPI: el paquete que se llama
# `ur` ahi es una libreria de notebooks, sin relacion. La implementacion de referencia en
# python es la de Foundation Devices (BSD-2-Clause-Patent), que no trae setup.py, asi que se
# copia el paquete pinneado por commit.
ARG UR_PY_COMMIT=a371f6355fb3433cc989ad5bf28f87a347b222fe
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone --quiet https://github.com/Foundation-Devices/foundation-ur-py.git /tmp/urpy \
    && git -C /tmp/urpy checkout --quiet "${UR_PY_COMMIT}" \
    && cp -r /tmp/urpy/ur "$(python3 -c 'import site; print(site.getsitepackages()[0])')/ur" \
    && cp /tmp/urpy/LICENSE /app/LICENSE.foundation-ur-py \
    && rm -rf /tmp/urpy \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    # Nada se instala en runtime: pip y setuptools son 12 MB de equipaje.
    && pip uninstall -y pip setuptools 2>/dev/null || true

COPY --from=fw /flash_image.bin /app/flash_image.bin
COPY --from=fw /qemu_efuse.bin /app/qemu_efuse.bin
COPY jxemu ./jxemu
COPY start.py .

# Umbrel crea app-data/<app-id> con owner 1000:1000.
USER 1000:1000
EXPOSE 6080
CMD ["python3", "start.py"]
