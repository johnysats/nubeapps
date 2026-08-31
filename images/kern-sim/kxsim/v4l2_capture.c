/* Camara virtual: reemplaza el driver V4L2 del simulador de upstream.
 *
 * En un contenedor no hay /dev/video0 (v4l2loopback es un modulo del kernel del host, y en
 * umbrelOS no esta), asi que este archivo se compila en lugar de
 * `simulator/platform/video_sim/v4l2_capture.c` y lee los frames que escribe el shim de
 * Python en un archivo.
 *
 * Por que no alcanza el `--qr-dir` de upstream: `load_configured_frame()` solo corre dentro
 * de `app_video_start()`, o sea una imagen por sesion de camara. Un PSBT no entra en un solo
 * QR y hay que animarlo. En cambio el camino del webcam llama a `v4l2_capture_read_rgb565()`
 * en cada vuelta del hilo de streaming, que es exactamente el enganche que hace falta.
 *
 * Formato del archivo (lo escribe kxsim/camera.py con rename atomico):
 *   magic "KRNF" | u32 width | u32 height | u32 seq | width*height*3 bytes RGB888
 *
 * El shim publica RGB888 y el empaquetado a RGB565 pasa aca: Pillow no trae packer a 565 y
 * hacerlo en Python son 230.000 iteraciones por frame.
 */
#include "v4l2_capture.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define KXSIM_MAGIC "KRNF"
#define KXSIM_HEADER_SIZE 16
/* Techo de sanidad: el shim escribe 640x480 (614 KB). */
#define KXSIM_MAX_FRAME_BYTES (8u * 1024u * 1024u)
/* Sin frame nuevo el hilo de streaming quedaria en busy loop: solo duerme cuando no hay
 * webcam. Reentregar el frame anterior mantiene el ritmo en ~30 fps. */
#define KXSIM_POLL_US 15000
#define KXSIM_OPEN_TIMEOUT_MS 5000

struct v4l2_capture {
  char *path;
  uint32_t width;
  uint32_t height;
  uint32_t last_seq;
};

/* Lee el archivo entero. Python escribe a un temporal y renombra, asi que un open() ve
 * siempre un frame completo, nunca uno a medio escribir. */
static uint8_t *read_frame_file(const char *path, size_t *out_size) {
  FILE *file = fopen(path, "rb");
  if (!file)
    return NULL;

  uint8_t header[KXSIM_HEADER_SIZE];
  if (fread(header, 1, sizeof(header), file) != sizeof(header) ||
      memcmp(header, KXSIM_MAGIC, 4) != 0) {
    fclose(file);
    return NULL;
  }

  uint32_t width, height, seq;
  memcpy(&width, header + 4, 4);
  memcpy(&height, header + 8, 4);
  memcpy(&seq, header + 12, 4);

  size_t payload = (size_t)width * height * 3u;
  if (width == 0 || height == 0 || payload > KXSIM_MAX_FRAME_BYTES) {
    fclose(file);
    return NULL;
  }

  uint8_t *buffer = malloc(KXSIM_HEADER_SIZE + payload);
  if (!buffer) {
    fclose(file);
    return NULL;
  }
  memcpy(buffer, header, KXSIM_HEADER_SIZE);
  size_t got = fread(buffer + KXSIM_HEADER_SIZE, 1, payload, file);
  fclose(file);

  if (got != payload) {
    free(buffer);
    return NULL;
  }
  *out_size = KXSIM_HEADER_SIZE + payload;
  return buffer;
}

static uint32_t frame_seq(const uint8_t *frame) {
  uint32_t seq;
  memcpy(&seq, frame + 12, 4);
  return seq;
}

v4l2_capture_t *v4l2_capture_open(const char *device, uint32_t desired_width,
                                  uint32_t desired_height) {
  (void)desired_width;
  (void)desired_height;
  if (!device)
    return NULL;

  /* El shim escribe el primer frame al arrancar, pero el firmware puede llegar antes. */
  uint8_t *frame = NULL;
  size_t size = 0;
  for (int waited = 0; waited < KXSIM_OPEN_TIMEOUT_MS; waited += 50) {
    frame = read_frame_file(device, &size);
    if (frame)
      break;
    usleep(50000);
  }
  if (!frame) {
    fprintf(stderr, "kxsim: no hay frames en %s\n", device);
    return NULL;
  }

  v4l2_capture_t *cap = calloc(1, sizeof(*cap));
  if (!cap) {
    free(frame);
    return NULL;
  }
  cap->path = strdup(device);
  memcpy(&cap->width, frame + 4, 4);
  memcpy(&cap->height, frame + 8, 4);
  /* La resolucion se negocia una sola vez: video_sim dimensiona su buffer con lo que
   * devuelve get_resolution() y despues no lo vuelve a mirar. El shim no la cambia. */
  cap->last_seq = frame_seq(frame) - 1u;
  free(frame);

  if (!cap->path) {
    free(cap);
    return NULL;
  }
  fprintf(stderr, "kxsim: camara virtual %ux%u desde %s\n", cap->width, cap->height, device);
  return cap;
}

void v4l2_capture_get_resolution(const v4l2_capture_t *cap, uint32_t *width, uint32_t *height) {
  if (!cap)
    return;
  if (width)
    *width = cap->width;
  if (height)
    *height = cap->height;
}

size_t v4l2_capture_read_rgb565(v4l2_capture_t *cap, uint8_t *rgb565_buf, size_t buf_size) {
  if (!cap || !rgb565_buf)
    return 0;

  uint8_t *frame = NULL;
  size_t size = 0;
  /* Igual que el driver real: espera un frame nuevo, con timeout de 1 s. */
  for (int waited = 0; waited < 1000000; waited += KXSIM_POLL_US) {
    frame = read_frame_file(cap->path, &size);
    if (frame && frame_seq(frame) != cap->last_seq)
      break;
    free(frame);
    frame = NULL;
    usleep(KXSIM_POLL_US);
  }
  if (!frame)
    return 0;

  cap->last_seq = frame_seq(frame);

  /* El buffer lo dimensiono video_sim con la resolucion negociada; si el shim publicara una
   * distinta se convierte lo que entra en vez de pisar memoria ajena. */
  size_t pixels = (size - KXSIM_HEADER_SIZE) / 3u;
  if (pixels > buf_size / 2u)
    pixels = buf_size / 2u;

  const uint8_t *rgb = frame + KXSIM_HEADER_SIZE;
  for (size_t i = 0; i < pixels; i++) {
    uint16_t value = (uint16_t)(((rgb[i * 3] & 0xF8u) << 8) | ((rgb[i * 3 + 1] & 0xFCu) << 3) |
                                (rgb[i * 3 + 2] >> 3));
    rgb565_buf[i * 2] = (uint8_t)(value & 0xFFu);
    rgb565_buf[i * 2 + 1] = (uint8_t)(value >> 8);
  }
  free(frame);
  return pixels * 2u;
}

void v4l2_capture_close(v4l2_capture_t *cap) {
  if (!cap)
    return;
  free(cap->path);
  free(cap);
}
