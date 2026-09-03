# Pagina propia + el widget "Blink Donate Button" para donar a johnysats, que mantiene este
# store. El repo del widget no tiene git tags ni releases (package.json declara una version
# pero nunca la etiqueta), asi que en vez de pinnear un tag como el resto de las apps se
# pinnea el commit que toco el archivo por ultima vez. No hay firma PGP que verificar:
# upstream no publica ninguna.
ARG DONATE_JS_COMMIT=b4a03fcedde903705a2fc2127849c7991adf81fe

FROM --platform=$BUILDPLATFORM alpine:3.22 AS fetch
ARG DONATE_JS_COMMIT
RUN apk add --no-cache curl libqrencode-tools
WORKDIR /out
RUN base="https://raw.githubusercontent.com/blinkbitcoin/donation-button.blink.sv/${DONATE_JS_COMMIT}"; \
    curl -fsSL -o blink-pay-button.js "${base}/js/blink-pay-button.js"; \
    mkdir -p img; \
    for f in blink-dark.svg blink-light.svg successcheckmark.svg; do \
      curl -fsSL -o "img/$f" "${base}/img/$f"; \
    done

# El widget, tal como lo publica Blink, sale a la red por su cuenta en cada carga: importa
# una fuente de Google, trae sus iconos de GitHub Pages y, si le hacen click al logo, manda
# la URL de tu Umbrel a get.blink.sv. Nada de eso es necesario para cobrar una factura y
# ninguna otra app de este store hace algo asi, con lo cual se corta aca.
#
# Cada parche verifica primero que su objetivo exista: si un bump del widget mueve alguna de
# estas lineas, el build falla en vez de publicar en silencio una version que vuelve a
# filtrar al usuario.
RUN set -eux; \
    js=blink-pay-button.js; \
    grep -q "@import url('https://fonts.googleapis.com" "$js"; \
    grep -q "https://blinkbitcoin.github.io/donation-button.blink.sv/img/" "$js"; \
    grep -q "params.append('embed_url', currentUrl);" "$js"; \
    # 1. la fuente de Google: el font-family ya declara fallbacks del sistema
    sed -i "/@import url('https:\/\/fonts.googleapis.com/d" "$js"; \
    # 2. los iconos del widget, ahora servidos por nosotros
    sed -i 's#https://blinkbitcoin.github.io/donation-button.blink.sv/img/#/img/#g' "$js"; \
    # 3. la URL del Umbrel del usuario, que viajaba como parametro de referido
    sed -i "/params.append('embed_url', currentUrl);/d" "$js"; \
    # y que efectivamente no haya quedado nada
    ! grep -q "fonts.googleapis.com\|blinkbitcoin.github.io\|embed_url" "$js"

# El QR de respaldo se genera aca: si el widget no carga (sin internet, API caida), la
# pagina igual muestra una direccion Lightning escaneable, sin depender de JavaScript.
RUN qrencode -t SVG -o img/lnaddress.svg -l M "lightning:johnysats@blink.sv"

FROM nginx:1.29-alpine
COPY --from=fetch /out/blink-pay-button.js /usr/share/nginx/html/blink-pay-button.js
COPY --from=fetch /out/img/ /usr/share/nginx/html/img/
COPY index.html /usr/share/nginx/html/index.html
COPY default.conf /etc/nginx/conf.d/default.conf
