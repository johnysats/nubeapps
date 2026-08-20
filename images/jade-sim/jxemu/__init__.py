"""Lo que falta para servir el emulador QEMU de Jade en Umbrel.

Upstream ya emula el dispositivo entero (`main/qemu/`): el firmware corre en
qemu-system-xtensa y expone la pantalla, los botones y la camara por un WebSocket. Lo que
agrega este paquete es la carcasa web (la pagina de upstream pide la webcam del navegador,
que el navegador solo entrega por HTTPS) y la camara virtual alimentada desde /files.
"""
