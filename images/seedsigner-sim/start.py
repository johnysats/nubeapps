#!/usr/bin/env python3
"""Punto de entrada del contenedor: instala el shim y arranca el firmware."""
import os
import sys

sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app")

# settings.py persiste en "settings.json" relativo al cwd fuera de SeedSigner OS.
os.chdir(os.environ.get("SSEMU_DATA_DIR", "/data"))

import ssemu

ssemu.install()

from main import main

main(["-l", os.environ.get("SSEMU_LOGLEVEL", "INFO")])
