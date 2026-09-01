# Parches al firmware upstream

Se aplican con `git apply` en el Dockerfile, sobre el tag que empaqueta `versions.yml`.
Si upstream cambia el archivo, el `git apply` falla y frena el build: esa es la señal de que
hay que revisar el parche, no un problema.

## 0001-sflash-guardar-solo-lo-que-cambio.patch

`simulator/sim_modules/sflash.py` (la flash SPI simulada, 8 MB en un archivo) tiene dos bugs
que hacen inusable al simulador apenas se guarda algo:

- **`save()` reescribe los 8 MB enteros en cada page program de 256 bytes.** Poner el PIN
  dispara cientos de escrituras: el proceso queda en estado D (I/O ininterrumpible), la
  pantalla se congela y el dispositivo parece colgado. Medido: 5,9 GB de I/O en un minuto.
  El parche guarda solo el rango que cambió, y hace que los `*_erase()` también persistan
  (upstream solo guardaba desde `write()`, así que un borrado sin escritura posterior se
  perdía).
- **Abre el archivo en modo texto (`'w'`) y le escribe un `bytearray`**, con lo cual el
  archivo queda en 0 bytes. Al arrancar de nuevo, `ext_settings.load()` lee un array vacío y
  el firmware muere con `IndexError: bytearray index out of range`. El parche usa `'wb'` y,
  además, completa con `0xff` un archivo corto: un guardado a medias (corte de luz) no puede
  dejar la app sin arrancar.

Vale un PR a upstream, como los dos flags de compilación de kern.
