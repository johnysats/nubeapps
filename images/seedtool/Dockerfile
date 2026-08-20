# Bitcoin Seed Tool servido como estatico: el build de upstream es un unico index.html
# autocontenido (JS y CSS inlineados, sin CDN ni fuentes externas).
#
# No lo compilamos desde fuente a proposito: package.json usa rangos "^" en todas las
# dependencias, asi que un build nuestro no seria reproducible ni identico al archivo que
# la comunidad audita. Bajamos el asset del release y verificamos su firma PGP contra la
# clave que viene vendorizada en este repo (no la del repo upstream: si les comprometen el
# repo, la clave tambien la cambian).
ARG SEEDTOOL_TAG=2.3.0

# El artefacto no depende de la arquitectura: siempre en la del builder, nunca bajo QEMU.
FROM --platform=$BUILDPLATFORM alpine:3.22 AS fetch
ARG SEEDTOOL_TAG
RUN apk add --no-cache curl gnupg
COPY RELEASE-SIGNING-KEY.asc /tmp/key.asc
WORKDIR /out
RUN set -eux; \
    base="https://github.com/BitcoinQnA/seedtool/releases/download/${SEEDTOOL_TAG}"; \
    curl -fsSL -o index.html "${base}/index.html"; \
    curl -fsSL -o signature.txt "${base}/signature.txt"; \
    gpg --batch --import /tmp/key.asc; \
    gpg --batch --verify signature.txt; \
    # El cuerpo firmado es "sha256sum index.html <hash>": lo damos vuelta al formato de
    # sha256sum -c. Se lee del texto ya verificado, no del archivo crudo.
    gpg --batch --output body.txt --decrypt signature.txt; \
    awk '$1 == "sha256sum" { print $3 "  " $2 }' body.txt > SHA256SUMS; \
    test -s SHA256SUMS; \
    sha256sum -c SHA256SUMS; \
    rm -f signature.txt body.txt SHA256SUMS

FROM nginx:1.29-alpine
ARG SEEDTOOL_TAG
COPY --from=fetch /out/index.html /usr/share/nginx/html/index.html
COPY default.conf /etc/nginx/conf.d/default.conf
COPY extra/compat.js extra/i18n.js extra/es.json /usr/share/nginx/extra/
# El nombre del archivo que se descarga para uso offline lleva la version.
RUN sed -i "s/__SEEDTOOL_TAG__/${SEEDTOOL_TAG}/" /etc/nginx/conf.d/default.conf
