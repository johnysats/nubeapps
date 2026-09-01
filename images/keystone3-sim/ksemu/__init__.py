"""Shim que corre el simulador de Keystone 3 Pro headless y lo sirve por web.

Upstream ya trae el simulador entero en `ui_simulator/`: LVGL sobre SDL2, con la flash y el
secure element simulados en archivos y el mismo core de firma en Rust que el dispositivo
real. Lo que agrega ksemu es solo lo que hace falta para servirlo en Umbrel:

    device.py   el proceso del simulador: arranque, reinicio y reset de fabrica
    screen.py   la ventana SDL capturada del Xvfb y publicada por long-poll
    remote.py   los toques de la pagina, que entran como mouse (para LVGL eso es el tactil)
    camera.py   la camara virtual: un archivo de la MicroSD escrito como QR ya decodificados
    webui.py    el servidor HTTP y la carcasa

Los tres cambios al arbol de upstream estan en ../patches (y el porque, en su LEEME.md).
"""
