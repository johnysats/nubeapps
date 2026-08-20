"""Shim para correr el simulador de Krux headless y manejarlo desde el navegador.

Upstream ya trae en `simulator/kruxsim/` los mocks de todo el hardware del K210; lo que
falta para servirlo en Umbrel es que no dependa de una ventana SDL ni de una webcam. Este
paquete agrega solo eso, sin tocar el arbol de upstream:

| Upstream                          | Que le pone kxemu                                   |
|-----------------------------------|-----------------------------------------------------|
| ventana SDL + `update_screen()`   | `screen.py`: SDL dummy y el frame publicado por HTTP |
| teclas y mouse de pygame          | `remote.py`: registrado donde va el sequence executor|
| `VideoCapture(0)` del mock sensor | `camera.py`: QR generado desde un archivo de la SD   |
"""
