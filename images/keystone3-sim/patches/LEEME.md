# Parches al simulador de upstream

Tres cambios, y los tres son la misma decision: **la camara del simulador tiene que ser un
archivo, no la pantalla del escritorio**.

Upstream compila el simulador con dos caminos para la camara (`ui_simulator/simulator_model.c`):

- con `GET_QR_DATA_FROM_SCREEN` (el que viene activo) el firmware **captura la pantalla real
  del escritorio** y busca un QR ahi. Es lo que hace el simulador en macOS: pones el QR en una
  ventana al lado y el dispositivo lo "ve". Necesita permisos de captura y un escritorio.
- sin ese define, lee las lineas de `ui_simulator/assets/qrcode_data.txt` y trata **cada linea
  como un QR ya decodificado**. Es el camino que la propia doc de upstream recomienda en Linux
  y Windows, y el que usa `ksemu/camera.py`.

Aca no hay escritorio -el contenedor corre headless- asi que se comenta el define (parche 1).

Los otros dos sacan del build el crate que implementa esa captura (`rust/sim_qr_reader`), y no
son opcionales aunque el codigo C ya no lo llame:

> **`SDL_Init()` segfaultea si el crate esta linkeado.** `sim_qr_reader` depende de
> `screenshots`, que arrastra una copia **estatica** de libdbus dentro de `librust_c.a` (240
> simbolos `dbus_*`). SDL2 usa la `libdbus-1.so` del sistema, y con las dos en el mismo proceso
> hay dos estados globales del mismo mutex: el crash es dentro de `pthread_mutex_lock` llamado
> desde dbus, en el primer `SDL_Init(SDL_INIT_VIDEO)`, antes de que el firmware dibuje nada.
> Pasa igual con `SDL_VIDEODRIVER=dummy`, con dbus instalado y bajo `dbus-run-session`: no es
> un problema de X ni de que falte el bus.

De paso, sin ese crate el binario tampoco necesita `-lxcb` (que hay que agregar a mano, porque
`CMAKE_EXE_LINKER_FLAGS` pone la libreria antes de los objetos y el linker la descarta).

Van como `sed` y no como `.patch`: son tres lineas sobre archivos que upstream toca seguido y
un `.patch` fallaria por contexto en cada bump. Cada paso verifica su patron y corta el build
con un mensaje claro si upstream lo cambio.
