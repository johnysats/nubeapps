#!/usr/bin/env python3
"""Genera los JSON de layout que el simulador lee de assets/.

Cada pantalla de transaccion se arma desde una plantilla JSON. El firmware la lleva
**embebida** como string en `gui_analyze.c`; el simulador, en cambio, la lee de un archivo
(`C:/assets/page_btc.json`), y upstream **no incluye esos archivos en el repo**: su doc te
manda a extraerlos a mano con un script que hay que editar cada vez (docs/SIMULATOR.md).

Sin ellos el simulador arranca igual, pero la pantalla de confirmar transaccion sale **vacia**
-titulo y boton de firmar, y un hueco negro donde iban el monto, el destino y la comision-,
que es justo lo que uno quiere mirar antes de firmar.

Este script saca las dos versiones del mismo `#ifndef COMPILE_SIMULATOR` -el string embebido y
el nombre del archivo- y escribe una con el nombre de la otra, asi que sigue a upstream sola
en cada bump.

    python3 extraer-layouts.py <arbol del firmware> <carpeta de salida>
"""
import json
import os
import re
import sys

# El JSON embebido y la ruta del archivo son las dos ramas del mismo #ifndef.
BLOCK = re.compile(r"#ifndef COMPILE_SIMULATOR\n(.*?)#else\n(.*?)#endif", re.S)
PATH = re.compile(r'PC_SIMULATOR_PATH\s+"/([\w.]+\.json)"')
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')

SOURCES = ["src/ui/gui_analyze/gui_analyze.c"]


def unescape(text):
    return text.replace('\\"', '"').replace("\\\\", "\\")


def main(tree, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for relative in SOURCES:
        source = open(os.path.join(tree, relative)).read()
        for embedded, simulated in BLOCK.findall(source):
            match = PATH.search(simulated)
            if not match:
                continue
            text = "".join(unescape(part) for part in STRING.findall(embedded))
            try:
                json.loads(text)
            except ValueError as error:
                sys.exit(f"ksemu: {match.group(1)} no quedo como JSON valido: {error}")
            with open(os.path.join(out_dir, match.group(1)), "w") as handle:
                handle.write(text)
            written.append(match.group(1))

    if not written:
        sys.exit("ksemu: no encontre ninguna plantilla; upstream cambio el patron "
                 "#ifndef COMPILE_SIMULATOR de gui_analyze.c")
    print("ksemu: plantillas generadas:", ", ".join(written))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
