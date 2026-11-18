"""Load (and keep loaded) the Whisper and NLLB engines for a given device."""

from __future__ import annotations

import threading
from typing import Callable

from . import models
from .settings import Settings

_lock = threading.Lock()
_cache: dict[str, tuple] = {}


def get_engines(settings: Settings, progress: Callable[[str], None] | None = None):
    """Return (WhisperAsr, NllbTranslator), downloading models on first use.

    Engines are cached per device so a second class doesn't reload ~5 GB of weights.
    """
    from .asr import WhisperAsr
    from .translate import NllbTranslator

    device = settings.resolved_device()
    with _lock:
        if device not in _cache:
            models.ensure_whisper(progress)
            models.ensure_nllb(progress)
            if progress:
                progress(f"Loading models on {device.upper()}...")
            asr = WhisperAsr(models.whisper_dir(), device, settings)
            tr = NllbTranslator(models.nllb_dir(), device)
            _cache[device] = (asr, tr)
        asr, tr = _cache[device]
        asr.settings = settings  # pick up changed VAD settings
        return asr, tr
