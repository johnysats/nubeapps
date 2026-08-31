"""Shim que corre el simulador de escritorio de Kern headless y lo sirve por web.

Upstream ya trae toda la capa de hardware falsa (`simulator/platform/`: FreeRTOS sobre
pthreads, NVS y SPIFFS en archivos, /sdcard en el filesystem). Lo que agrega kxsim es solo lo
que hace falta para servirlo en Umbrel, sin tocar el arbol de upstream:

    device.py   el proceso del simulador: arranque, reinicio y reset de fabrica
    screen.py   la ventana SDL capturada del Xvfb y publicada por long-poll
    remote.py   los toques de la pagina, que entran como mouse (para LVGL eso es el tactil)
    camera.py   la camara virtual: un archivo de la MicroSD codificado como QR
    webui.py    el servidor HTTP y la carcasa

El unico archivo de upstream que se reemplaza es el driver V4L2 (v4l2_capture.c): en el
contenedor no hay /dev/video0. Ver el comentario ahi.
"""
