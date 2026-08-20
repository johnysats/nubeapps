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
| `versions.yml` | tags upstream que se empaquetan (fuente única de verdad) |
| `.github/workflows/images.yml` | build multi-arch en runners nativos → GHCR + pin de digests |
| `.github/workflows/upstream-check.yml` | chequeo diario de releases upstream → PR de bump |

## Reglas duras de Umbrel (no negociables)

- **Prohibido `build:`** en los compose. Imagen pública, `linux/amd64` + `linux/arm64`,
  pinneada `repo:tag@sha256:<digest>` con el digest del **índice**, no el de una arquitectura.
- Servicio `app_proxy` solo con `environment`: `APP_HOST: <app-id>_<servicio>_1` y `APP_PORT`
  (puerto interno). El `port:` del manifest es el puerto externo, distinto de `APP_PORT`, y
  tiene que ser único en el host.
- No tocar `PROXY_AUTH_ADD`: la auth de Umbrel viene activa por defecto.
- Persistencia solo por bind mounts `${APP_DATA_DIR}/data/...`; dirs vacíos se commitean con
  `.gitkeep`. Nada de named volumes ni `/var/run/docker.sock`.
- Umbrel crea `app-data/<app-id>` con owner `1000:1000` → servicios con `user: "1000:1000"`.
- Los `*.template` top-level pasan por `envsubst`: **no** meter ahí configs con variables
  propias (`$host`, `$http_upgrade` de nginx se destruyen). Por eso la config de nginx va
  horneada en la imagen `ccq1-web`.
- En updates Umbrel solo copia `docker-compose.yml`, `*.template`, `exports.sh`, `torrc` y
  `hooks/`. Cualquier otro archivo de runtime queda viejo en instalaciones existentes.

## nubeapps-ccq1

```
app_proxy → web (nginx) ─┬─ /       → sim:6080   (noVNC + websockify)
                         └─ /files  → files:80   (filebrowser, --baseurl /files)
```

Flujo del PSBT: `/files` → `${APP_DATA_DIR}/data/work/MicroSD` → `/sd` del firmware.
Se firma con **Ready To Sign** del menú principal y sale como `<nombre>-signed.psbt`.

Decisiones que no son obvias:

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

**App nueva:** agregarle su entrada a `versions.yml` (con eso ya entra al chequeo diario y al pin
de digests) y sumar su job de build en `images.yml` — eso sí es específico de cada imagen, porque
define contexto, plataformas y si compila nativo o alcanza QEMU.

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

El recorrido que prueba las tres vías de una: `Load Mnemonic → Via Camera → QR Code` con un
`.txt` de 12 palabras en `/tmp/kxdata/sd` (cámara), y después `Sign → PSBT → Load from SD card`
con un PSBT en la misma carpeta, que deja el firmado como `<nombre>-signed.psbt` (MicroSD).

Verificación real = instalar por umbrelOS (`umbreld client apps.install.mutate --appId
nubeapps-ccq1`), abrir en el navegador, subir y firmar un PSBT, reiniciar y confirmar que los
datos siguen.
