#!/usr/bin/env python3
"""Punto de entrada del contenedor: instala el shim y arranca el firmware."""
import os
import shutil
import sys

sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app")

# settings.py persiste en "settings.json" relativo al cwd fuera de SeedSigner OS.
os.chdir(os.environ.get("SSEMU_DATA_DIR", "/data"))

# LEEME + seed de ejemplo la primera vez: una carpeta vacia no dice como se usa. Solo si no
# hay ningun archivo, asi que si el usuario ya guardo lo suyo (o borro el LEEME) no vuelve.
SD_DIR = os.environ.get("SSEMU_SD_DIR", "/data/MicroSD")
HELP_DIR = "/app/help"
try:
    os.makedirs(SD_DIR, exist_ok=True)
    if not any(name for name in os.listdir(SD_DIR) if not name.startswith(".")):
        for name in os.listdir(HELP_DIR):
            shutil.copyfile(os.path.join(HELP_DIR, name), os.path.join(SD_DIR, name))
except OSError as error:
    print("ssemu: no pude dejar la ayuda en la MicroSD:", error)

import ssemu

ssemu.install()

from main import main

main(["-l", os.environ.get("SSEMU_LOGLEVEL", "INFO")])
