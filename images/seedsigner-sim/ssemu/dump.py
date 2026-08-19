"""Volcado del PSBT firmado a la carpeta compartida.

En el dispositivo real el PSBT firmado solo sale por QR animado. Aca ademas lo
escribimos como archivo para poder bajarlo desde /files y cerrar el ciclo dentro de
Umbrel. El QR animado se sigue mostrando igual.
"""
import logging
from pathlib import Path

from ssemu import camera

logger = logging.getLogger(__name__)

last_signed = None


def install():
    from seedsigner.views import psbt_views

    view_cls = psbt_views.PSBTSignedQRDisplayView
    original_run = view_cls.run

    def run(self):
        try:
            _write_signed(self.controller.psbt)
        except Exception:
            logger.exception("ssemu: no se pudo volcar el PSBT firmado")
        return original_run(self)

    view_cls.run = run


def _write_signed(psbt):
    global last_signed

    source_path = camera.source.resolve()
    stem = source_path.stem if source_path else "psbt"
    if stem.endswith("-signed"):
        stem = stem[: -len("-signed")]

    target = Path(camera.source.directory) / f"{stem}-signed.psbt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(psbt.serialize())
    last_signed = target.name
    logger.info(f"ssemu: PSBT firmado escrito en {target}")
