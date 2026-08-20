"""Ampliar la pantalla sin que el texto se convierta en una escalera.

El panel del dispositivo son 320x170 y las fuentes del firmware son bitmap de un pixel de
grosor: no hay mas resolucion que sacarle, la unica decision es como se agranda.

- Vecino mas cercano: fiel, cada pixel es un cuadrado. Los trazos diagonales de los digitos
  quedan escalonados.
- EPX/Scale2x: el algoritmo clasico de pixel art. Duplica la imagen mirando los cuatro
  vecinos de cada pixel y solo rellena las esquinas donde hay una diagonal, asi que los
  bordes rectos siguen igual de nitidos y los curvos dejan de ser escalones. No inventa
  colores nuevos (a diferencia de un filtro bilineal, que emborrona todo el texto).
"""
import numpy as np
from PIL import Image


def _epx(array):
    """Un paso de EPX: devuelve el array al doble de ancho y alto."""
    height, width = array.shape[:2]
    padded = np.pad(array, ((1, 1), (1, 1), (0, 0)), mode="edge")
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]

    def same(one, other):
        return np.all(one == other, axis=-1)

    # Las cuatro reglas de EPX, tal cual: una esquina toma el color del vecino solo cuando
    # ese vecino coincide con el de al lado y difiere de los otros dos, o sea cuando el
    # pixel esta sobre una diagonal. En un borde recto no se cumple ninguna y no cambia nada.
    up_left = same(left, up) & ~same(left, down) & ~same(up, right)
    up_right = same(up, right) & ~same(up, left) & ~same(right, down)
    down_left = same(down, left) & ~same(down, right) & ~same(left, up)
    down_right = same(right, down) & ~same(right, up) & ~same(down, left)

    output = np.empty((height * 2, width * 2, array.shape[2]), dtype=array.dtype)
    output[0::2, 0::2] = np.where(up_left[..., None], up, center)
    output[0::2, 1::2] = np.where(up_right[..., None], right, center)
    output[1::2, 0::2] = np.where(down_left[..., None], left, center)
    output[1::2, 1::2] = np.where(down_right[..., None], down, center)
    return output


def upscale(image, scale, smooth):
    """Amplia `scale` veces; con `smooth` usa EPX en las potencias de dos que entren."""
    if scale <= 1:
        return image
    if not smooth:
        return image.resize((image.width * scale, image.height * scale), Image.NEAREST)

    # EPX solo sabe duplicar, asi que para los factores que no son potencia de dos se pasa
    # de largo y se baja al tamano pedido promediando (BOX). Terminar con un vecino mas
    # cercano a factor fraccionario seria peor que no suavizar: repetiria unas filas si y
    # otras no, que es exactamente el defecto que se estaba tratando de sacar.
    array = np.asarray(image)
    factor = 1
    while factor < scale:
        array = _epx(array)
        factor *= 2
    result = Image.fromarray(array)
    target = (image.width * scale, image.height * scale)
    return result if result.size == target else result.resize(target, Image.BOX)
