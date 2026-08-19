# Firmware de SeedSigner (upstream, sin parches) + el shim ssemu que reemplaza el
# hardware. Umbrel no permite `build:` en los compose: la imagen tiene que venir hecha
# y multi-arch. Aca no se compila nada nativo, asi que alcanza con buildx normal.
ARG SEEDSIGNER_TAG=0.8.7

FROM python:3.11-slim-bookworm AS builder
ARG SEEDSIGNER_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --recurse-submodules trae seedsigner-translations (las 22 traducciones); el submodulo
# seedsigner-screenshots esta marcado update=none y no se clona.
RUN git clone --depth 1 --branch "${SEEDSIGNER_TAG}" --recurse-submodules --shallow-submodules \
        https://github.com/SeedSigner/seedsigner.git /app

# numpy no esta en requirements.txt pero hardware/camera.py lo necesita:
# Image.fromarray(frame.astype(...)) solo funciona con arrays de numpy.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt numpy Babel

WORKDIR /app
# Los .po del submodulo son fuentes: sin compilar a .mo la UI queda toda en ingles.
RUN /opt/venv/bin/pybabel compile -f -d src/seedsigner/resources/seedsigner-translations/l10n \
    && /opt/venv/bin/pip uninstall -y Babel \
    && find /app -name .git -prune -exec rm -rf {} + \
    && rm -rf /app/tests /app/docs /app/enclosures /app/l10n


FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive

# zbar: decodificacion de los QR que "ve" la camara. qrencode: helpers/qr.py lo llama
# por subprocess para dibujar los QR que muestra el dispositivo.
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 qrencode \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
COPY ssemu /app/ssemu
COPY start.py /app/start.py

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SSEMU_DATA_DIR=/data \
    SSEMU_SD_DIR=/data/MicroSD \
    SSEMU_PORT=6080

# uid/gid 1000: Umbrel crea app-data/<app-id> con ese owner
RUN groupadd -g 1000 ss && useradd -m -u 1000 -g 1000 -s /bin/bash ss \
    && mkdir -p /data/MicroSD && chown -R 1000:1000 /data /app

USER 1000:1000
WORKDIR /data
EXPOSE 6080
CMD ["python3", "/app/start.py"]
