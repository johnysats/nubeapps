# NubeApps — Umbrel Community App Store

Repo único que umbrelOS sincroniza como app store comunitario. Cada carpeta `nubeapps-*` es
una app instalable. `id` del store: `nubeapps` (prefija obligatoriamente cada app id).

## Estructura

| Ruta | Qué es |
|---|---|
| `umbrel-app-store.yml` | id + name del store |
| `nubeapps-ccq1/` | app: simulador Coldcard Q1 + explorador de la MicroSD para PSBTs |
| `nubeapps-seedsigner/` | app: simulador SeedSigner + cámara virtual alimentada desde `/files` |
| `nubeapps-krux/` | app: simulador Krux (Maix Amigo táctil) + MicroSD y cámara virtual desde `/files` |
| `images/ccq1-simulator/` | Dockerfile del simulador (firmware compilado dentro de la imagen) |
| `images/ccq1-web/` | nginx que rutea `/` → sim:6080 y `/files` → filebrowser (lo usan las tres apps) |
| `images/seedsigner-sim/` | firmware de SeedSigner upstream + el shim `ssemu` que reemplaza el hardware |
| `images/krux-sim/` | firmware de Krux upstream + el shim `kxemu` que lo corre headless |
| `nubeapps-jadeplus/` | app: simulador Blockstream Jade Plus (firmware real en QEMU) + cámara virtual desde `/files` |
| `images/jade-sim/` | firmware de Jade compilado para QEMU + el shim `jxemu` que le pone carcasa web |
| `nubeapps-seedtool/` | app: Bitcoin Seed Tool servido como estatico + capa de traduccion ES |
| `images/seedtool/` | nginx + el `index.html` firmado del release, con `i18n/` inyectado por `sub_filter` |
| `nubeapps-kern/` | app: simulador Kern (ESP32-P4 táctil) + MicroSD y cámara virtual desde `/files` |
| `images/kern-sim/` | simulador de escritorio de Kern + el shim `kxsim` que lo corre headless |
| `nubeapps-passport/` | app: simulador Passport 2 (Gen 1.2) + MicroSD y cámara virtual desde `/files` |
| `images/passport-sim/` | firmware de Passport 2 compilado nativo + el shim `pxemu` que le pone carcasa web |
| `nubeapps-keystone3/` | app: simulador Keystone 3 Pro (solo-Bitcoin) + MicroSD y cámara virtual desde `/files` |
| `images/keystone3-sim/` | simulador de escritorio de Keystone (upstream) + el shim `ksemu` que lo sirve por web |
| `nubeapps-donate/` | app: página para donar al mantenedor del store (widget de Blink) |
| `images/donate/` | nginx + el widget de Blink vendorizado y despojado de sus llamadas externas |
| `images/*/help/` | `LEEME.txt` + `ejemplo-seed-publica.txt`, sembrados en la carpeta compartida |
| `versions.yml` | tags upstream que se empaquetan (fuente única de verdad) |
| `.github/workflows/images.yml` | build multi-arch en runners nativos → GHCR + pin de digests |
| `.github/workflows/upstream-check.yml` | chequeo diario de releases upstream → PR de bump |

**De dónde saca el usuario los PSBT y las seeds**: cada carcasa web tiene un `<details>`
"¿De dónde saco estos archivos?" al pie del panel de la cámara (en ccq1, debajo de la barra),
y el arranque copia `images/<img>/help/` a la carpeta compartida **solo si está vacía** —
`.gitkeep` no cuenta, y si el usuario ya guardó algo o borró el LEEME no vuelve a aparecer.
La seed de ejemplo es el vector de test público (`abandon … about`), y el archivo tiene solo
las 12 palabras: un comentario ahí rompería el parseo de la cámara.

## Reglas duras de Umbrel (no negociables)

- **Prohibido `build:`** en los compose. Imagen pública, `linux/amd64` + `linux/arm64`,
  pinneada `repo:tag@sha256:<digest>` con el digest del **índice**, no el de una arquitectura.
- Servicio `app_proxy` solo con `environment`: `APP_HOST: <app-id>_<servicio>_1` y `APP_PORT`
  (puerto interno). El `port:` del manifest es el puerto externo, distinto de `APP_PORT`, y
  tiene que ser único en el host.
- No tocar `PROXY_AUTH_ADD`: la auth de Umbrel viene activa por defecto.
- **Todas las apps comparten una sola red Docker** (`umbrel_main_network`, que umbreld le
  inyecta a cada compose). El nombre corto del servicio queda como alias DNS en esa red, así
  que `sim`, `files` o `web` resuelven a los contenedores de **todas** las apps instaladas a
  la vez, round-robin. Entre contenedores hay que hablarse por el nombre completo
  `<app-id>_<servicio>_1` — que es lo que umbreld fuerza con `container_name` — y nunca por
  el nombre corto. Por eso `ccq1-web` recibe `SIM_HOST` y `FILES_HOST` por environment en vez
  de tenerlos horneados.
- Persistencia solo por bind mounts `${APP_DATA_DIR}/data/...`; dirs vacíos se commitean con
  `.gitkeep`. Nada de named volumes ni `/var/run/docker.sock`.
- Umbrel crea `app-data/<app-id>` con owner `1000:1000` → servicios con `user: "1000:1000"`.
- Los `*.template` top-level pasan por `envsubst`: **no** meter ahí configs con variables
  propias (`$host`, `$http_upgrade` de nginx se destruyen). Por eso la config de nginx va
  horneada en la imagen `ccq1-web`; lo único variable son los dos upstreams, que resuelve el
  envsubst del entrypoint de nginx acotado con `NGINX_ENVSUBST_FILTER`.
- En updates Umbrel solo copia `docker-compose.yml`, `*.template`, `exports.sh`, `torrc` y
  `hooks/`. Cualquier otro archivo de runtime queda viejo en instalaciones existentes.

## nubeapps-ccq1

```
app_proxy → web (nginx) ─┬─ /       → sim:6080   (noVNC + websockify)
                         └─ /files  → files:80   (filebrowser, --baseurl /files)
```

Flujo del PSBT: `/files` → `${APP_DATA_DIR}/data/work/MicroSD` → `/sd` del firmware.
Se firma con **Ready To Sign** del menú principal y sale como `<nombre>-signed.psbt`.

Flujo del QR: `/files` → `MicroSD/QR-Camara/` → `qrfeed.py` → `work/qrdata.txt` → escáner del
firmware. El PSBT firmado vuelve como BBQr en la pantalla (se lee del navegador).

Decisiones que no son obvias:

- **La "cámara" es un archivo, no hay cámara virtual**: `unix/variant/sim_scanner.py` de upstream
  no abre ningún dispositivo; mientras la pantalla de escaneo está abierta hace polling de
  `qrdata.txt` en el cwd del firmware (`unix/work`, que es justo el bind mount) y toma **cada
  línea como un QR ya decodificado**. `qrfeed.py` solo traduce "apareció un archivo en
  `MicroSD/QR-Camara`" a ese archivo: `.psbt` binario → base64, texto → una línea por QR
  (las que empiezan con `#` se ignoran), y un PSBT partido en varias líneas se vuelve a unir en
  una sola. Como llega decodificado no hay tamaño máximo ni hace falta BBQr ni animar nada.
- **El orden importa y no se puede evitar**: el task del escáner se guarda el mtime al arrancar,
  así que un archivo que ya estaba cuando se abrió la pantalla no se lee. Primero el escáner en
  el dispositivo, después subir el archivo — está dicho en la carcasa y en el LEEME de la carpeta.
- **El mtime se fuerza a crecer** al escribir `qrdata.txt`: la comparación de upstream es en
  segundos, y dos escaneos dentro del mismo segundo perderían el segundo.
- **`QR-Camara` no cuenta para el sembrado de la ayuda**: `start.sh` la crea en cada arranque,
  así que el `ls -A` que decide si la MicroSD está vacía la excluye.

- **`Xvfb 640x1024` + `x11vnc -clip`**: SDL crea la ventana en `position=(100,100)` fija
  (`unix/simulator.py`), y sin window manager X respeta esa coordenada. El framebuffer tiene
  que ser mayor que 518×853 (el `q1-images/background.png`) o el dispositivo sale cortado.
  `start.sh` calcula el recorte con `xwininfo` por nombre de ventana, así que se ajusta solo.
- **Sin window manager**: el teclado igual llega (probado con `xdotool`, PointerRoot alcanza).
- **`xterm` instalado aunque no se vea**: `simulator.py` corre el firmware dentro de un xterm;
  lo abre en `+650+40`, fuera del recorte.
- **Poda de la imagen** (2.86 GB → 1.06 GB): antes de borrar `external/`, `stm32/`, `graphics/`
  y `misc/` hay que resolver los symlinks de `shared/` que apuntan ahí, o el firmware no bootea
  (`ImportError: no module named 'public_constants'`).
- `SIM_ARGS=--q1 -l` → PIN 12-12 sin seed. **Sin `-l` el simulador arranca con una seed de test
  pública hardcodeada.**

## nubeapps-seedsigner

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, MJPEG + botones)
                                          └─ /files → files:80  (filebrowser)
```

El firmware de SeedSigner se clona por tag **sin parchear**: los tres puntos de contacto con el
hardware se reemplazan desde `images/seedsigner-sim/ssemu/`, instalando módulos falsos en
`sys.modules` antes de importar `seedsigner` (`start.py`).

| Hardware | Qué lo reemplaza |
|---|---|
| `RPi.GPIO` (botones) | `ssemu/fake_gpio.py`: 8 pines en memoria. `hardware/buttons.py` queda intacto, con su debounce y su screensaver |
| ST7789 por SPI | `ssemu/display.py`: subclase de `BaseDisplayDriver` + monkeypatch del factory; cada frame va a un `FrameBuffer` |
| `picamera` | `ssemu/camera.py`: la "escena" es un archivo de `/files` codificado como QR (animado si es PSBT) |

Decisiones que no son obvias:

- **Sin X11 ni VNC** (a diferencia de ccq1): el display de SeedSigner ya es un `PIL.Image`.
- **La pantalla va por long-poll (`/frame.jpg?seq=N`), no por el MJPEG de `/stream`**: la
  conexión infinita del MJPEG se atasca en los reverse proxies (con code-server delante daba
  10-12 s de demora por click, porque los POST quedaban encolados detrás del stream). `/stream`
  sigue existiendo para curl.
- **El pin se mantiene bajo hasta que el firmware lo lee** (con timeout de 2 s por si esa
  pantalla no escucha esa tecla). Con un pulso de duración fija, todo click que caía mientras
  el thread principal renderizaba —o sea, fuera del bucle de `wait_for`— se perdía entero.
- **`action=down`/`up` además de `tap`**: la página manda down/up con el mouse y el teclado, así
  el pin queda bajo mientras mantenés apretado y la repetición continua la hace el firmware con
  sus tiempos. El único gap artificial (270 ms) es entre dos taps de la *misma* tecla, porque
  `buttons.py` descarta repeticiones dentro de 250 ms; entre teclas distintas no hay espera.
- **El modo entropía se detecta por el stack de llamadas**, no por la resolución: `scan` pide
  480x480 y la entropía por imagen 240x240, los dos cuadrados. Si viene de
  `gui/screens/tools_screens.py` servimos ruido de `os.urandom`; si no, el QR.
- **Los QR de la cámara se dibujan con la lib `qrcode`, no con `helpers/qr.py`**: ese helper
  llama a `qrencode` y escribe siempre en `/tmp/qrcode.png`, que el dispositivo usa a la vez
  para sus propios QR (carrera entre threads).
- **numpy no está en el `requirements.txt` de upstream** pero hace falta:
  `Camera.read_video_stream` hace `frame.astype(...)`.
- **Los `.po` del submódulo `seedsigner-translations` hay que compilarlos** (`pybabel compile`)
  o la UI queda toda en inglés.
- El único enganche que depende de nombres internos de upstream es
  `PSBTSignedQRDisplayView.run` (volcado del PSBT firmado a `/files`); si cambia en 0.9.0, el
  import falla ruidosamente al arrancar.

## nubeapps-krux

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, long-poll + táctil)
                                          └─ /files → files:80  (filebrowser sobre la MicroSD)
```

Upstream ya trae en `simulator/kruxsim/` los mocks de todo el hardware del K210 (los usa su CI
para las capturas de la doc). Lo que agrega `images/krux-sim/kxemu/` es solo lo que falta para
servirlo en Umbrel, sin tocar el árbol de upstream:

| Upstream | Qué le pone kxemu |
|---|---|
| ventana SDL + `update_screen()` | `screen.py`: `SDL_VIDEODRIVER=dummy` y el frame publicado por HTTP |
| teclas y mouse de pygame | `remote.py`: se registra donde va el "sequence executor" |
| `VideoCapture(0)` del mock `sensor` | `camera.py`: QR armado con un archivo de la MicroSD |

Decisiones que no son obvias:

- **El enganche es `register_sequence_executor()`**, la API que upstream usa para guionar
  capturas: `buttons` y `sensor` le leen `.key` y `.camera_image` a ese objeto. **No se
  registra en `pmu`**: el botón de encendido también consume `key == K_UP`, así que
  compartirlo con PAGE_PREV apagaría el dispositivo cada dos por tres.
- **El táctil no pasa por ahí**: `TCOMMON.current_point()` lee el mouse de SDL, así que se
  reemplaza por el último `POST /api/touch`. La página manda la posición relativa (0..1)
  porque el tamaño en pantalla depende del zoom; `to_screen_pos()` de upstream la traduce de
  la ventana al LCD. El punto se mantiene hasta que el firmware lo lee al menos una vez (con
  timeout de 2 s), si no un click rápido se pierde entre dos renders.
- **`sys.modules["qrcode"]` es del firmware, no de PyPI**: el mock lo pisa con el módulo que
  usa el dispositivo para dibujar sus propios QR. `start.py` guarda antes la librería de PyPI
  como `kxemu_qrcode`; sin eso la cámara virtual devuelve MagicMocks y la pantalla muestra
  `ValueError: cannot determine region size`.
- **Nada de `pathlib` en el shim**: el mock `uos` parchea `os.stat()` para reescribir las
  rutas `/sd`, y un `PosixPath` ahí revienta con `AttributeError: startswith`.
- **Los QR de la cámara van en formato `pXofN`**, el mismo que anima el firmware: partir un
  PSBT en base64 en trozos de 240 bytes evita el QR gigante de una sola pieza. El mock pone
  `camera_image = None` cuando decodifica una parte, y ese setter es el que avanza a la
  siguiente.
- **El modo entropía se detecta por el stack de llamadas** (igual que en seedsigner): si viene
  de `pages/capture_entropy.py` se sirve ruido de `os.urandom`, porque esa pantalla mide la
  desviación de píxeles y un QR no pasa el umbral.
- **`sd` y `flash` son symlinks**: upstream corre desde `simulator/` (busca ahí `assets/` y
  las fuentes `.bdf`), pero krux guarda en rutas relativas al cwd. Los symlinks apuntan a los
  bind mounts en vez de mover ninguna de las dos convenciones.
- **De MaixPy solo se clonan los `board.py`** (sparse checkout del commit que el tag pinnea) y
  el módulo nativo `uUR` se instala desde su repo (`selfcustody/cUR`, 1.8 MB): clonar MaixPy
  entero serían más de 2 GB para tres archivos.
- **La imagen pesa 553 MB y el 45% son ruedas que no se pueden achicar**: opencv (87 MB, lo
  importan los mocks `lcd` y `sensor`), numpy (68 MB), pygame (45 MB), Pillow (25 MB). Lo que
  sí se recortó: de las fuentes `.bdf` solo quedan las dos del Amigo (`unifont-16` y
  `FusionPixel-14` son de los modelos a botones y sumaban 13 MB), pip se borra del venv y no
  se instalan las libSDL de apt, porque la rueda de pygame ya trae las suyas en `pygame.libs`.
- **`machine.reset()` no puede terminar el proceso**: cambiar el tema, restaurar settings de
  fábrica o apagar pasan por ahí, y el mock lo traduce a un `QUIT` de pygame. Upstream cierra
  la ventana y sale; acá eso dejaba el contenedor muerto y la pantalla congelada. `screen.py`
  lo trata como el reset del K210 y hace `os.execv` del proceso. Apagar y reiniciar se
  distinguen por un solo dato: `PowerManager.shutdown()` duerme el PMU antes
  (`enter_sleep_mode`) y `reboot()` no. Con Shutdown la pantalla queda negra y la página
  muestra **Encender** (`POST /api/power`), que es lo que rearranca.

## nubeapps-jadeplus

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, long-poll)
                                          └─ /files → files:80  (filebrowser)
```

Acá no hay shim de hardware: upstream ya emula el dispositivo entero. El firmware real de
ESP32 corre en `qemu-system-xtensa` (el build de Espressif, que existe para amd64 y arm64) y
expone pantalla, botones y cámara por un WebSocket dentro del contenedor. `jxemu` es solo el
puente entre eso y el navegador:

| Upstream | Qué le pone jxemu |
|---|---|
| `display.html` que pide la webcam del navegador | `webui.py` + `static/`: pantalla por long-poll, sin `getUserMedia` (Umbrel sirve por HTTP y ahí no existe) |
| WebSocket del firmware | `device.py`: frames RGB565 → PIL, botones y camara |
| cámara real | `camera.py`: un archivo de `/files` como QR (UR `crypto-psbt` animado si es PSBT, SeedQR si son 12/24 palabras) |

Decisiones que no son obvias:

- **La config `BOARD_TYPE_QEMU_LARGER` es la del Jade Plus**: 320x170, la misma que
  `BOARD_TYPE_JADE_V2_ANY`. Se activa con `switch_to.sh qemu --dev --psram --webdisplay-larger`
  y pide una imagen de carcasa (`main/qemu/jadel.png`) que **upstream no tiene en el repo**: sin
  ese archivo el build de CMake se cae, así que va uno de 1x1 (la página de upstream no se usa).
  La máquina de QEMU es `esp32`, no `esp32s3`: es el firmware de Jade con la pantalla del Plus.
- **La cámara es *pull***: el firmware manda el comando `1` cada vez que quiere un frame y se
  queda bloqueado en la cola (`esp_camera_fb_get`). Mandarle frames de motu proprio le cuelga
  el servidor web de adentro y el dispositivo deja de responder: uno por pedido.
- **El framebuffer es RGB565 big-endian**: leerlo little-endian no rompe nada visible a primera
  vista —los grises salen bien— pero desteñe todos los colores, porque el verde queda partido
  entre los dos bytes. Y los 5 bits se estiran replicando los altos (31 → 255), no con un shift.
- **La toolchain va atada al tag**: cada release declara en su `Dockerfile.qemu` con qué imagen
  `blockstream/jade_builder` se compila. Con la de otra versión el firmware ni linkea
  (`implicit declaration of esp_image_bootloader_offset_set`), así que `images.yml` saca ese
  digest del tag que se está empaquetando en vez de pinnearlo a mano.
- **El `RUN` del firmware corre con bash**: `export.sh` del IDF 5.5 falla con dash
  ("Activation script failed") y después no existe `idf.py`. Y el script que arma la imagen de
  flash cambió de nombre entre releases (`make-flash-img.sh` / `make_flash_img.sh`) y en las
  viejas no acepta argumentos: se lo llama por glob y sin parámetros.
- **El binario de qemu viene con símbolos de debug**: 72 MB que `strip` deja en 17.
- **El puerto 30121 (serial sobre TCP) no se publica**: es la vía para conectar Green o
  Sparrow, pero sería un puerto sin la autenticación de Umbrel. La app es solo por QR.
- **El encoder de UR no está en PyPI**: el paquete llamado `ur` es una librería de notebooks
  sin relación (y arrastra Jupyter). Se copia el de Foundation Devices, pinneado por commit.

## nubeapps-seedtool

```
app_proxy → web (nginx) ─┬─ /          → index.html del release (13 MB, autocontenido)
                         ├─ /extra/    → compat.js + i18n.js + es.json (inyectados con sub_filter)
                         └─ /download  → el mismo archivo, sin tocar, como descarga
```

No es un simulador: Bitcoin Seed Tool es una sola pagina HTML sin CDN ni fuentes externas, asi
que la app es nginx + un archivo. Sin bind mounts, sin estado, contenedor `read_only`.

Decisiones que no son obvias:

- **No se compila desde fuente**: todas las deps de upstream son rangos `^`, un build propio no
  seria reproducible ni identico al archivo que audita la comunidad. El Dockerfile descarga el
  `index.html` del release y verifica su firma PGP contra `RELEASE-SIGNING-KEY.asc` vendorizada
  **en este repo** (no la del repo upstream: si les comprometen el repo, la clave tambien).
- **`/download` no pasa por `sub_filter`**: la copia offline tiene que seguir dando el mismo
  sha256 que publica y firma Bitcoin QnA. Existe porque el boton de descarga de upstream apunta
  a GitHub, inutil en una maquina airgapped.
- **Sin HTTPS la pagina no arranca**: `thisBrowserIsShit()` exige `crypto.subtle` y
  `navigator.clipboard`, que los navegadores solo exponen en un contexto seguro, y umbrelOS
  publica en `http://umbrel.local:PUERTO`. `extra/compat.js` repone las dos cosas antes de que
  corra ese chequeo (el firmware lo dispara en `DOMContentLoaded`; nosotros vamos inyectados
  antes). De WebCrypto solo se usa `digest("SHA-256")` en 5 lugares -checksum de BIP-39, del
  one-time pad y del split en 3 tarjetas-, asi que el shim implementa solo eso y **rechaza**
  cualquier otro algoritmo en vez de devolver un hash incorrecto en silencio. `getRandomValues`,
  que es lo que genera entropia, no se toca: existe igual sin contexto seguro.
- **La traduccion no forkea nada**: upstream no tiene i18n (1156 strings hardcodeados). El
  diccionario `extra/es.json` (~1050 entradas, 93% de los caracteres visibles) lo aplica
  `extra/i18n.js` sobre el DOM, inyectado con `sub_filter` antes de `</body>`. Lo que no este en
  el diccionario queda en ingles, y un bump de version no rompe nada.
- **El selector es un ES|EN con las dos opciones a la vista**, metido en la `header.topbar` de
  upstream (antes del ojo de datos privados). Un boton solo con "EN" no se leia como selector de
  idioma. La primera visita muestra una burbuja "Espanol / English" que se cierra al primer
  click; ese enganche se conecta 2,5 s despues de cargar, porque el firmware hace clicks propios
  al arrancar (abre el panel About) y si no la cerraba solo.
- **El cartel "Load seed first" no esta en el DOM**: es un `::after` del CSS de upstream, asi
  que la unica forma de traducirlo es pisar la regla con `html[lang="es"]`.
- **Traduce por texto completo del nodo**, con los espacios internos colapsados para la
  busqueda: nunca toca `TEXTAREA`, `CODE`, `PRE`, `SCRIPT` ni nada con `data-no-i18n`, asi los
  datos del usuario (seeds, xpubs, PSBTs) quedan intactos aunque coincidan con una clave.
- **El `MutationObserver` se desconecta antes de cada recorrido masivo**: si queda escuchando,
  las reescrituras del propio `walk()` le vuelven como mutaciones y retraduce lo que se acaba de
  devolver al ingles.
- **Dos funciones tocan la red desde el navegador**: los avatares PayNym (`paynym.rs`, con
  checkbox) y el resolver BIP-353 por DoH. No se bloquean con CSP a proposito -romperlas seria
  mutilar la herramienta-, se documentan en el manifest.

Probar sin navegador (montar `i18n/` como volumen evita rebuildear):

```sh
docker build -t seedtool:test images/seedtool
docker run -d --name sttest --read-only --tmpfs /var/cache/nginx --tmpfs /var/run \
  -p 127.0.0.1:18615:80 -v "$PWD/images/seedtool/i18n:/usr/share/nginx/i18n:ro" seedtool:test

curl -s localhost:18615/download | sha256sum      # tiene que dar el hash del signature.txt
curl -s localhost:18615/ | grep -o "/extra/compat.js"   # la inyeccion
```

Las pruebas viven en `images/seedtool/extra/` y no se copian a la imagen:

| Script | Que verifica |
|---|---|
| `sha-test.js` | el SHA-256 del shim contra `node:crypto`: largos de borde, vistas con offset, vectores FIPS y que SHA-512 sea rechazado |
| `gate-test.js` | que el chequeo de upstream bloquee sin el shim y pase con el, y que `getRandomValues` quede intacto |
| `ui-test.js` | Playwright: el selector visible en la topbar, el cambio ES/EN, la burbuja de primera visita y el movil |
| `collect.js` | Playwright: recorre las herramientas y lista el texto visible que **no** cubre `es.json` (es lo que hay que revisar en cada bump) |
| `shots.js` | Playwright: capturas de varias pantallas en espanol, para leer el texto como lo ve el usuario |

Necesitan `playwright` y `jsdom`, instalados **globales en el server** (`/usr/lib/node_modules`,
con `NODE_PATH` exportado en `~/.bashrc`, asi sirven para cualquier proyecto) y el
preview levantado. La capa ES tambien se probo con jsdom: cargar el `index.html`, evaluar
`i18n.js` con un `fetch` que devuelva `es.json`, y chequear que el toggle deja el ingles byte a
byte igual.

## nubeapps-kern

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, long-poll + táctil)
                                          └─ /files → files:80  (filebrowser sobre la MicroSD)
```

Kern es el signer en C para ESP32-P4 de odudex (el mismo de Krux), y **upstream ya trae un
simulador de escritorio** en `simulator/`: SDL2 + LVGL, con toda la capa de hardware falsa
hecha (FreeRTOS sobre pthreads, NVS y SPIFFS en archivos, `/sdcard` en el filesystem). No hay
que emular nada; `kxsim` solo lo sirve por web:

| Upstream | Qué le pone kxsim |
|---|---|
| ventana SDL con `lv_sdl_mouse` | `screen.py`: el firmware corre contra un Xvfb y la ventana se captura de ahí |
| mouse de SDL | `remote.py`: los toques de la página entran con `xdotool` (para LVGL el mouse *es* el táctil) |
| `--qr-dir` de `video_sim` | `v4l2_capture.c` + `camera.py`: frames de verdad, ver abajo |

Decisiones que no son obvias:

- **No compila sin dos flags.** En aarch64 libwally toma el `smix` de NEON porque `__ARM_NEON`
  está definido, pero ese archivo está escrito para el NEON de 32 bits: se arregla con
  `-flax-vector-conversions`, el mismo flag que le pone el `configure` de libwally. Y upstream
  solo prueba el build Debug, donde glibc no marca `fread()` como `warn_unused_result`: en
  Release ese `-Werror` frena el build en `efuse_hmac_sim.c`. Debug no es opción, el login hace
  PBKDF2 de 100.000 iteraciones. Los dos merecen un PR a upstream.
- **La cámara entra por el driver de webcam, no por `--qr-dir`**: `load_configured_frame()` solo
  corre dentro de `app_video_start()`, o sea **una imagen por sesión de cámara**, y un PSBT no
  entra en un solo QR. El camino del webcam, en cambio, pide un frame nuevo en cada vuelta del
  hilo de streaming. Se compila con `-DSIM_WEBCAM=ON` y se reemplaza `v4l2_capture.c` (cuatro
  funciones, target aislado) por uno que lee los frames que publica el shim en un archivo.
- **`--webcam=<ruta>` va pegado con `=`**: upstream lo declara `optional_argument` y
  `getopt_long` descarta el valor si viene separado por un espacio (abre `/dev/video0` y falla).
- **La cámara publica exactamente 600x600**, el tamaño del preview de wave_4b. El firmware
  recorta y escala el frame con el PPA antes de decodificar, pero `ppa_do_scale_rotate_mirror()`
  en el simulador es un **memcpy que no transforma**: con cualquier otro tamaño el decodificador
  reinterpreta los bytes con otra geometría y los QR densos salen "Unrecognized format". Otro
  board pide recalcularlo (wave_35 usa 320x320).
- **El QR se dibuja con módulos de un número entero de píxeles** (`box_size`), nunca chico y
  reescalado: a un tamaño que no sea múltiplo exacto de la cuadrícula los módulos quedan de 7 y
  8 px alternados y el firmware falla de a ratos.
- **El shim publica RGB888 y el driver empaqueta a RGB565**: Pillow no trae packer a 565 y
  hacerlo en Python son 230.000 iteraciones por frame. Los frames van a `/run/kxsim` (tmpfs).
- **El modo ruido para la entropía es un botón**, no una detección: el firmware corre en otro
  proceso y no hay pila de llamadas para mirar como en krux y seedsigner.
- **La carpeta compartida es la raíz de la MicroSD** (`/data/sdcard`), no `sdcard/kern`: el
  firmware guarda ahí sus backups pero los PSBT firmados van a la raíz (`signed-N.txt`).
- **Un `docker restart` deja huérfano el lock `/tmp/.X99-lock`** y Xvfb se niega a arrancar:
  `start.py` lo borra antes.
- **El PIN no protege nada**: el eFuse simulado usa una clave fija de 32 bytes `0x42`, así que
  las palabras anti-phishing tampoco son las del hardware. Va dicho en el manifest y el LEEME.

**El bump upstream no pide prueba manual.** Kern publica un tag por semana y es el único
firmware del store que se puede probar sin ojos humanos: `images/kern-sim/smoke.py` levanta la
imagen, carga la seed pública por la cámara virtual, le escanea un PSBT (dos partes: prueba el
QR animado), lo firma y **verifica con embit que la firma es de la clave derivada de esa seed**.
Corre en CI como el job `kern-smoke`, tarda ~40 s y sube las capturas de cada paso como
artefacto si falla. Ojo con dos cosas al tocarlo: el arranque pasa por un splash **quieto**, que
sin la espera fija se confunde con la pantalla final, y los taps van por coordenadas relativas,
así que un cambio de layout de upstream lo rompe — que es justamente la señal que se busca.

```sh
docker build -t kern-sim:test images/kern-sim
python3 images/kern-sim/smoke.py kern-sim:test --shots /tmp/shots   # necesita pillow + embit

docker run -d --name kxtest -p 127.0.0.1:6080:6080 -v /tmp/kxdata:/data \
  -e KXSIM_VERBOSE=1 -v "$PWD/images/kern-sim/kxsim:/app/kxsim:ro" kern-sim:test

curl -XPOST localhost:6080/api/touch -d "x=0.5&y=0.9&action=down"   # y &action=up para soltar
curl -XPOST localhost:6080/api/camera -d "file=seed.txt&noise=0"    # noise=1 para la entropía
curl -XPOST localhost:6080/api/factory-reset                        # borra nvs/ y spiffs/
curl -s localhost:6080/frame.png -o /tmp/shot.png
```

## nubeapps-passport

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, long-poll)
                                          └─ /files → files:80  (filebrowser sobre la MicroSD)
```

Upstream trae un simulador que compila el firmware de Passport 2 como binario nativo de
MicroPython y lo maneja desde una ventana SDL. `pxemu` reemplaza esa ventana, nada más: no
hay que emular hardware.

| Upstream | Qué le pone pxemu |
|---|---|
| ventana SDL de `simulator/simulator.py` | `device.py`: los cinco pipes del binario, sin X11 ni SDL |
| teclado y mouse de pygame/SDL | `webui.py`: `POST /api/button` con `down`/`up`/`tap` |
| cámara real | `camera.py`: un archivo de la MicroSD como QR (SeedQR numérico o UR animado) |

Decisiones que no son obvias:

- **La flash SPI simulada de upstream está rota y hay que parchearla**
  (`patches/0001-sflash-guardar-solo-lo-que-cambio.patch`, el porqué en `patches/LEEME.md`):
  `sim_modules/sflash.py` reescribe los 8 MB en cada page program de 256 bytes —poner el PIN
  deja el proceso en estado D con 5,9 GB de I/O y **el dispositivo parece congelado**— y guarda
  en modo texto un bytearray, con lo que el archivo queda en 0 bytes y al reiniciar el firmware
  muere con `IndexError` en `ext_settings.load()`. Vale un PR a upstream.
- **Solo la variante color (Gen 1.2)**: `make color` en `simulator/`. La mono ya no se fabrica.
- **Compila nativo en las dos arquitecturas, sin cross**: el Rust de `extmod/foundation-rust`
  va contra el host (1.77.1 + cbindgen 0.26.0), así que el job de `images.yml` usa un runner
  por arquitectura y arma el índice después, como el de kern.
- **De todo el árbol clonado sobreviven cuatro rutas**: el binario (con `strip`: sale con
  símbolos de debug), `simulator/` (sim_boot + sim_modules), los módulos de Passport y
  `extmod/uasyncio`, el único paquete importable de extmod. `MICROPYPATH` los busca en ese
  orden y ahí termina el árbol de 1 GB.
- **La cola nativa del keypad tiene 16 slots** (`ports/unix/ring_buffer.h`): mandar teclas a
  ciegas sin esperar el redibujo la satura y el dispositivo parece colgado. Un tap dura ~300 ms.
- **El "Shutdown" del menú apaga el contenedor**: el firmware sale con 0, `start.py` lo traduce
  a un exit 1 y el `restart: on-failure` del compose lo vuelve a levantar. Sin esa traducción
  la app quedaría muerta hasta reinstalarla.
- **Los iconos ‹ › del pie de pantalla son los botones laterales `x` / `y`**, no el navpad. El
  onboarding pide un Security Check con Envoy que se saltea con `x` → `y`.
- **El PIN y las palabras anti-phishing no protegen nada**: la flash SPI es un archivo, no hay
  secure element. Va dicho en el manifest y en el LEEME.
- Salidas de la firma: por MicroSD queda `<nombre>-signed-001.psbt` + `<nombre>-final-001.txn`
  y **el PSBT original se borra**; por QR el firmado se muestra en pantalla y el botón izquierdo
  (`x`) lo guarda en `microsd/transactions/QR-signed-001.psbt`, **en hexadecimal** (no
  binario ni base64, a diferencia del que sale por la MicroSD).

**Ojo con los logs**: MicroPython no es tty acá y su stdout sale bufferado, así que
`docker logs` llega tarde y desordenado. La señal es el `X-Frame-Seq` de `/frame.png`, y ni esa
alcanza tecla a tecla (el cursor del PIN parpadea y mueve el seq solo): presionar con ~1 s de
separación y mirar la captura.

```sh
docker build -t passport-sim:test images/passport-sim
docker run -d --name pxtest --user 1000:1000 -p 127.0.0.1:6081:6080 -v /tmp/pxdata:/data \
  passport-sim:test

curl -XPOST localhost:6081/api/button -d "key=y&action=down"   # y = seleccionar, x = atras
curl -XPOST localhost:6081/api/camera -d file=seed.txt      # a que archivo apunta la camara
curl -s localhost:6081/frame.png -o /tmp/shot.png           # la pantalla
```


## nubeapps-keystone3

```
app_proxy → web (misma imagen ccq1-web) ─┬─ /      → sim:6080  (carcasa web, long-poll + táctil)
                                          └─ /files → files:80  (filebrowser sobre la MicroSD)
```

Upstream trae en `ui_simulator/` el simulador entero: LVGL sobre SDL2, con la flash y el
secure element simulados en archivos y el **mismo core de firma en Rust** que el dispositivo
real. No hay que emular hardware; `ksemu` solo lo sirve por web, como `kxsim` con kern:

| Upstream | Qué le pone ksemu |
|---|---|
| ventana SDL de `ui_simulator/main.c` | `screen.py`: el firmware corre contra un Xvfb y la ventana se captura de ahí |
| mouse de SDL | `remote.py`: los toques de la página entran con `xdotool` (para LVGL el mouse *es* el táctil) |
| `assets/qrcode_data.txt` | `camera.py`: escribe ahí el archivo elegido como QR ya decodificados |

Se empaqueta la variante **btc_only** (`-DBTC_ONLY=true`): menos Rust que compilar y la UI sin
las veinte cadenas que no vienen al caso. El firmware trae **español nativo** (y ruso, chino,
coreano): es la única app del store cuya UI se lee en español sin capa nuestra.

Decisiones que no son obvias:

- **Sin las plantillas JSON, la pantalla de firmar sale vacía.** Cada pantalla de transacción
  se arma desde un JSON que el firmware lleva embebido como string, pero el simulador lee de
  un archivo (`C:/assets/page_btc.json`) que **upstream no incluye en el repo**: su doc te
  manda a extraerlo a mano. Sin él se ven el título y el botón de firmar, y un hueco negro
  donde iban el monto, el destino y la comisión. `extraer-layouts.py` saca las dos ramas del
  mismo `#ifndef COMPILE_SIMULATOR` -el string embebido y el nombre del archivo- y escribe
  una con el nombre de la otra, así que sigue a upstream sola en cada bump. `start.py` las
  copia a `assets/` en cada arranque, pisando: son de la imagen, no del usuario.
- **`SDL_Init()` segfaultea si `sim_qr_reader` está linkeado**: ese crate arrastra una copia
  estática de libdbus dentro de `librust_c.a` (240 símbolos `dbus_*`) que choca con la
  `libdbus-1.so` que usa SDL2, y el crash es en el primer `SDL_Init`, antes de dibujar nada.
  Pasa igual con `SDL_VIDEODRIVER=dummy` y bajo `dbus-run-session`. Se lo saca del build, que
  además es lo que queremos: es el lector de QR **por captura de pantalla**, el camino de
  macOS. Ver `images/keystone3-sim/patches/LEEME.md`.
- **La cámara es un archivo, igual que en ccq1**: sin ese crate, el firmware lee
  `assets/qrcode_data.txt` al abrir la pantalla de escaneo y toma **cada línea como un QR ya
  decodificado**. Como llega decodificado no hay tamaño máximo: el PSBT va en un solo
  `ur:crypto-psbt` (el límite es del firmware: 100 KB y 3000 líneas). **El orden importa**:
  primero elegir el archivo, después entrar a escanear. Un reinicio deja la cámara sin
  escena, porque la selección vive en memoria del shim.
- **La MicroSD casi no firma**: `home_more_sign_by_sdcard` ("Firmar desde la tarjeta Micro SD",
  el visor filtra `ONLY_PSBT`) solo entra en el menú `…` del home si
  `GetCurrentWalletIndex() != SINGLE_WALLET`, o sea con la billetera activa en multifirma
  (`gui_widgets/btc_only/gui_home_widgets.c`). Con single-sig todo va por QR. La tarjeta sirve
  igual para importar/exportar una config multifirma, exportar el archivo de conexión desde la
  pantalla de xpubs y actualizar firmware.
- **`assets/` es la unidad `C:` de LVGL**, resuelta como `./ui_simulator/assets` relativa al
  cwd (`lv_conf.h`: `LV_FS_STDIO_PATH`), así que el proceso corre desde `/app/sim` y ahí hay
  un symlink a `/data/assets`. La MicroSD es un bind mount **anidado** en
  `/data/assets/sd`, para que sea la misma carpeta que ve `/files`.
- **El submódulo `keystone3-firmware-release` es privado (404)**: hay que clonar sin
  `--recursive` e inicializar solo `external/ctaes`.
- **El simulador no está en el CI de upstream** (solo corren checks de Rust), así que un tag
  nuevo puede no compilar. El binario se compila en Debug (es lo que hace `build.py -o
  simulator`) y pesa 25 MB con símbolos: va con `strip`.
- **El PIN y las palabras anti-phishing no protegen nada**, y además **el TRNG está
  mockeado** (`TrngGet()` devuelve bytes deterministas, `SE_GetTRng()` usa `rand()`): una
  billetera creada dentro del simulador es predecible. Va dicho en el manifest, en el LEEME y
  en la carcasa.
- **La cola de taps aguanta, pero no a ciegas**: tipeando las 12 palabras de una seed se
  pierde alguno cada tanto. Hay que verificar por captura entre pasos, como en passport.

**El bump upstream no pide prueba manual**, igual que kern: `images/keystone3-sim/smoke.py`
levanta la imagen, hace todo el alta (idioma español, PIN, nombre), tipea las 12 palabras de
la seed pública, le escanea un PSBT por la cámara virtual, lo firma y **lee de la pantalla el
QR animado del PSBT firmado** para verificar con embit que la firma es de la clave derivada de
esa seed. Corre en CI como el job `keystone3-smoke`, tarda ~4 min y sube las capturas de cada
paso como artefacto si falla. Tres cosas al tocarlo: los QR se leen del frame entero con
`zbarimg` (sin recortar, así un cambio de layout no obliga a recalcular el recorte) y el UR
fountain se reensambla **dentro del contenedor**, que es donde vive la librería `ur`, así el
runner solo necesita `pillow`, `embit` y `zbar-tools`; los taps van por coordenadas de la
pantalla de 480x800, así que un cambio de layout de upstream lo rompe — que es la señal que se
busca; y las palabras se tipean por el prefijo que deja una sola sugerencia (`aban`, `abou`).

```sh
docker build -t keystone3-sim:test images/keystone3-sim
python3 images/keystone3-sim/smoke.py keystone3-sim:test --shots /tmp/shots  # pillow+embit+zbarimg
docker run -d --name ksapp --user 1000:1000 -p 127.0.0.1:16081:6080 \
  -v /tmp/ksdata/assets:/data/assets -v /tmp/ksdata/microsd:/data/assets/sd keystone3-sim:test

curl -XPOST localhost:16081/api/touch -d "x=0.5&y=0.82&action=down"   # y &action=up para soltar
curl -XPOST localhost:16081/api/camera -d file=unsigned.psbt          # a que archivo apunta la camara
curl -s localhost:16081/frame.png -o /tmp/shot.png                    # la pantalla
```

## nubeapps-donate

```
app_proxy → web (nginx) ─┬─ /                    → index.html (página propia)
                         ├─ /blink-pay-button.js → el widget, servido desde acá
                         └─ /img/                → iconos del widget + QR de la dirección
```

No es un simulador ni tiene estado: nginx `read_only` sirviendo una página con el botón de
donación de Blink, apuntado a `johnysats`. Sin bind mounts.

Decisiones que no son obvias:

- **El widget se vendoriza pinneado por commit, no por tag**: el repo de Blink no publica
  releases ni git tags, así que `versions.yml` guarda en `tag` el commit que tocó el `.js`
  por última vez y lleva `auto_bump: false` — el chequeo diario saltea esa entrada en vez de
  avisar todos los días que no encontró tags. El bump es manual (el `curl` a la API de
  GitHub está en el comentario de `versions.yml`).
- **El widget, tal como lo publica Blink, sale a la red por su cuenta**: importa IBM Plex
  Sans de `fonts.googleapis.com`, trae tres iconos de `blinkbitcoin.github.io` y, al hacer
  click en el logo, manda `embed_url` —la URL de tu Umbrel— a `get.blink.sv`. Nada de eso
  hace falta para cobrar una factura, y ninguna otra app del store hace algo así, así que el
  Dockerfile lo saca con tres `sed`. **Cada `sed` verifica antes que su objetivo exista**: si
  un bump del widget mueve esas líneas el build falla, en vez de publicar en silencio una
  versión que vuelve a filtrar al usuario. Queda una sola conexión, `api.blink.sv/graphql`,
  que es la que crea la factura.
- **La dirección Lightning y su QR están siempre visibles**, no solo cuando el widget falla:
  quien ya tiene la billetera abierta prefiere escanear. El QR se genera con `qrencode` en el
  build, así no depende de JavaScript. Y el reintento del widget está acotado a 5 s: sin tope
  quedaba en un loop mudo.
- **`pay.blink.sv/johnysats` está roto** (HTTP 500), por eso el respaldo es la Lightning
  address `johnysats@blink.sv`, que sí resuelve LNURL.
- **El copiar al portapapeles tiene fallback a `execCommand`**: `navigator.clipboard` no
  existe sin contexto seguro y umbrelOS sirve por HTTP (el mismo motivo que en seedtool).
- **Los números de la página se escriben a mano**, con la fecha de corte a la vista. Salen de
  `git` y de los transcripts de las sesiones; medirlos en el build ataría la imagen a cada
  commit del repo. Ojo con los tokens: en los `.jsonl` el objeto `usage` **aparece dos veces
  por línea**, así que un `grep -o` sobre todo el archivo los cuenta al doble.

`page-test.js` (jsdom, no se copia a la imagen) cubre lo que importa que no se rompa: el
idioma según el navegador, el remontado del widget al cambiarlo, y que **sin widget la página
siga permitiendo pagar** — un fallo de red ahí es una donación perdida.

```sh
docker build -t donate:test images/donate
docker run -d --name donatetest --read-only --tmpfs /var/cache/nginx --tmpfs /var/run \
  -p 127.0.0.1:18619:80 donate:test

curl -s localhost:18619/blink-pay-button.js | grep -c "fonts.googleapis\|github.io\|embed_url"  # 0
node images/donate/page-test.js                       # 16 chequeos, tarda 6 s por el timeout
rsvg-convert -w 600 /tmp/ln.svg -o /tmp/ln.png && zbarimg -q --raw /tmp/ln.png   # el QR
```

## Actualizar el firmware

`versions.yml` en la raíz es la única fuente de verdad: una entrada por firmware upstream, con
su repo, el filtro de tags que le sirve, el tag empaquetado, la versión visible, la carpeta de la
app, el `ARG` del Dockerfile y las imágenes de GHCR que se tagean con esa versión.

1. `.github/workflows/upstream-check.yml` (cron diario) recorre **todas** las entradas de
   `versions.yml`, compara contra el último tag upstream que pasa el filtro y, si hay novedad,
   abre un PR que bumpea `versions.yml`, el `ARG` del Dockerfile y el `version:` del manifest.
2. Al mergear, `images.yml` reconstruye las imágenes y el job `pin` recorre otra vez
   `versions.yml` para escribir el digest del índice multi-arch en los `docker-compose.yml`
   (el sed toca `nubeapps-*`, así `ccq1-web` queda igual en las dos apps que lo usan).
3. Queda manual a propósito: changelog upstream, `releaseNotes` (EN/ES) y probar el simulador.
   umbrelOS ofrece la actualización cuando cambia `version:` del manifest.

Bump a mano: editar `versions.yml` y pushear a `main` (o `workflow_dispatch`).

**Cambio de una imagen compartida** (hoy `ccq1-web`, que usan siete apps): ahí el `-N` va
**solo en el manifest** de cada app afectada, no en `versions.yml`. El `version` de
`versions.yml` es el tag de la imagen de ESE firmware, y bumpearlo reconstruiría y
republicaría siete simuladores que nadie probó en ese ciclo — justo lo que el paso `changed`
evita. La imagen compartida se republica con su tag de siempre y el `pin` reparte el digest
nuevo a los siete compose. El próximo bump upstream vuelve a alinear manifest y `versions.yml`.

**Cambio solo del paquete** (sin firmware nuevo): umbrelOS solo ofrece actualizar cuando cambia
`version:` del manifest, así que se publica con sufijo `-N` (`6.6.0QX-2`) en `versions.yml` y en
el manifest — el sufijo también es el tag de la imagen en GHCR. El PR del chequeo diario lo
reemplaza por la versión limpia en el próximo bump upstream.

**App nueva:** agregarle su entrada a `versions.yml` (con eso ya entra al chequeo diario y al pin
de digests) y sumar su job de build en `images.yml` — eso sí es específico de cada imagen, porque
define contexto, plataformas y si compila nativo o alcanza QEMU — más su línea en el paso
`changed` del job `versions` (contexto + clave de `versions.yml` + **los nombres de sus jobs**),
que es lo que decide si esa imagen se reconstruye en cada push. Sin esa línea el job nunca corre.
Y sumar su fila a la tabla "Apps" del `README.md` (logo en `assets/`, link a la carpeta,
descripción y puerto): es el listado que ve cualquiera que entra al repo, y se olvida siempre.

**Solo se reconstruye lo que cambió:** cada job de build corre si cambió su contexto en `images/`,
el `tag`/`version` que empaqueta, o **sus propios jobs de `images.yml`**; si no, queda *skipped* y
el `pin` deja su digest como está (el tag en GHCR sigue apuntando al mismo índice). Los jobs se
comparan uno por uno con `yq` contra la versión anterior del workflow, no el archivo entero:
agregar una app suma jobs nuevos sin tocar los viejos, y por eso no reconstruye lo que ya estaba
(antes sí lo hacía, y el `pin` dejaba a las otras apps con imágenes que nadie había probado en ese
ciclo). Se reconstruye **todo** cuando cambia lo global —`on:`, `env:`, que lleva el `REGISTRY`
destino de todas— o cuando no hay contra qué comparar: `workflow_dispatch`, rama nueva, workflow
recién creado. Ojo con dispararlo a mano sobre una rama: reconstruye las seis imágenes y mueve los
tags flotantes de GHCR, así que el `pin` de esa rama va a repinnear apps que no tocaste.

## Probar

```sh
# build local (arm64, ~10 min la primera vez)
cd images/ccq1-simulator && docker build -t ccq1-simulator:test .

# stack de preview en el server (puerto 18611, solo localhost + IP de Tailscale)
cd /opt/ccq1-preview && sudo docker compose -p ccq1preview up -d

# captura del simulador sin browser
docker exec ccq1preview-sim-1 python3 -c \
  "from PIL import ImageGrab; ImageGrab.grab(xdisplay=':99').crop((100,100,618,953)).save('/tmp/p.png')"
```

Para iterar sobre `qrfeed.py` y la ayuda sin recompilar el firmware (~10 min), alcanza con
montarlos sobre la imagen publicada. `xdotool` no viene en la imagen: se instala en el
contenedor de prueba con `docker exec -u 0`.

```sh
docker run -d --name ccq1qr --user 1000:1000 -p 127.0.0.1:16080:6080 -v /tmp/ccq1qr/work:/sim/firmware/unix/work \
  -v "$PWD/images/ccq1-simulator/qrfeed.py:/usr/local/bin/qrfeed.py:ro" \
  -v "$PWD/images/ccq1-simulator/start.sh:/usr/local/bin/start.sh:ro" \
  -v "$PWD/images/ccq1-simulator/help:/usr/local/share/ccq1-help:ro" \
  ghcr.io/johnysats/ccq1-simulator:<tag> bash /usr/local/bin/start.sh   # el start.sh del repo no es ejecutable

docker exec -e DISPLAY=:99 ccq1qr xdotool key super+r     # tecla QR (META+r; n=NFC, l=lámpara)
cp unsigned.psbt /tmp/ccq1qr/work/MicroSD/QR-Camara/      # con el escáner ya abierto
docker logs ccq1qr | grep qrfeed                          # qué entregó y cuántos QR
```

Manejando el dispositivo con `xdotool`: las flechas y ENTER (`Return`) llegan con `key` a secas,
pero **las historias de texto ignoran un ENTER corto** — hay que bajar hasta el final y soltarlo
con `keydown Return; sleep 0.6; keyup Return`, si no parece colgado. Y ojo con clickear sobre la
pantalla: el simulador lo interpreta como pegar el portapapeles al escáner.

Para el simulador de SeedSigner, sin navegador (montar `ssemu/` como volumen evita rebuildear
en cada cambio):

```sh
docker build -t seedsigner-sim:test images/seedsigner-sim
docker run -d --name sstest -p 127.0.0.1:6080:6080 -v /tmp/ssdata:/data \
  -v "$PWD/images/seedsigner-sim/ssemu:/app/ssemu:ro" seedsigner-sim:test

curl -XPOST localhost:6080/api/button -d key=KEY_DOWN   # KEY_UP/DOWN/LEFT/RIGHT/PRESS, KEY1..3
curl -XPOST localhost:6080/api/button -d "key=KEY_DOWN&action=down"   # y &action=up para soltar
curl -XPOST localhost:6080/api/camera -d file=unsigned.psbt
curl -s localhost:6080/frame.png -o /tmp/shot.png       # la pantalla, para inspeccionarla
docker logs sstest | grep Executing                     # qué View está corriendo
```

Para el simulador de Krux, igual (montar `kxemu/` como volumen evita rebuildear en cada
cambio). El táctil se maneja con coordenadas relativas al frame, así que se puede guiar a
ciegas mirando `frame.png`:

```sh
docker build -t krux-sim:test images/krux-sim
docker run -d --name kxtest -p 127.0.0.1:6080:6080 -v /tmp/kxdata:/data \
  -v "$PWD/images/krux-sim/kxemu:/app/kxemu:ro" krux-sim:test

curl -XPOST localhost:6080/api/touch -d "x=0.5&y=0.27&action=down"   # y &action=up para soltar
curl -XPOST localhost:6080/api/button -d key=ENTER      # ENTER / PAGE / PAGE_PREV
curl -XPOST localhost:6080/api/camera -d file=seed.txt  # a qué archivo apunta la cámara
curl -s localhost:6080/frame.png -o /tmp/shot.png       # la pantalla, para inspeccionarla
```

Para el simulador de Jade hay que tener en cuenta que el firmware tarda ~50 min en compilar
(1351 objetos) y que el stage que lo compila es amd64: en un server arm64 hay que registrar
binfmt (`docker run --privileged --rm tonistiigi/binfmt --install amd64`). Para iterar sobre
`jxemu` sin recompilarlo, conviene guardar el `flash_image.bin` de un build anterior y armar
un Dockerfile que empiece en el `FROM python` y lo copie del contexto:

```sh
docker build -t jade-sim:test images/jade-sim
docker run -d --name jxtest -p 127.0.0.1:6080:6080 -v /tmp/jxdata:/data jade-sim:test

curl -XPOST localhost:6080/api/button -d key=next       # prev / next (rueda) / select (frontal)
curl -XPOST localhost:6080/api/camera -d file=seed.txt  # a qué archivo apunta la cámara
curl -s "localhost:6080/frame.png?scale=3&smooth=1" -o /tmp/shot.png   # la pantalla
```

El recorrido que prueba todo: un `.txt` con 12 palabras en `/tmp/jxdata/files` y
`Scan SeedQR` (la wallet queda activa con su fingerprint), y después un PSBT en la misma
carpeta y `Scan QR`, que tiene que llegar a mostrar las salidas y el monto.

El recorrido que prueba las tres vías de una: `Load Mnemonic → Via Camera → QR Code` con un
`.txt` de 12 palabras en `/tmp/kxdata/sd` (cámara), y después `Sign → PSBT → Load from SD card`
con un PSBT en la misma carpeta, que deja el firmado como `<nombre>-signed.psbt` (MicroSD).


**Keystone 3 Pro.** Recorrido verificado (pantalla 480x800; la API toma relativas:
x/480, y/800). Entre paso y paso hay que **mirar la captura**: mandar la secuencia entera a ciegas pierde algun tap.

| Pantalla | Toques |
|---|---|
| bienvenida | flecha (240,655) |
| idioma | Español (433,648), flecha (395,743) |
| verificacion y firmware | Omitir (407,96), Omitir (407,96) |
| nueva billetera | Importar billetera (240,750), Entiendo (240,743) |
| PIN nuevo | `1` (84,532) x6, Continuar-PIN-debil (112,747), `1` x6 |
| nombre | una letra, p.ej. `k` (380,645), flecha (429,767) |
| metodo | Frase unica secreta (240,460), 12 Palabras (240,554) |
| 12 palabras | `a`(50,697) `b`(286,755) `n`(334,755) `o`(406,640) `u`(311,640), sugerencia (70,583), borrar (35,755), confirmar (446,755) |
| home | ESCANEAR (240,733), menu … (438,96), atras (40,96) |
| desbloqueo | `1` (84,447) x6 — **otro layout** que el PIN del setup |
| PIN al firmar | `1` (84,532) x6 |
| deslizar para firmar | arrastre en y=0.93 de x=0.18 a x=0.98 |

El PSBT firmado sale como QR animado (UR fountain) en la pantalla: se lee capturando ~16
frames, recortando `360x360+60+166`, escalando 200% y pasandolos por `zbarimg -q --raw`.

Verificación real = instalar por umbrelOS (`umbreld client apps.install.mutate --appId
nubeapps-ccq1`), abrir en el navegador, subir y firmar un PSBT, reiniciar y confirmar que los
datos siguen.
