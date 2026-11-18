"""Download Whisper and download + convert NLLB (one-time setup).

Run directly to set everything up:  uv run python -m classnotes.models
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from . import paths

WHISPER_REPO = "large-v3"  # resolved by faster-whisper to Systran/faster-whisper-large-v3
NLLB_REPO = "facebook/nllb-200-distilled-600M"
NLLB_TOKENIZER_FILES = [
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]

Progress = Callable[[str], None] | None


def whisper_dir() -> Path:
    return paths.models_dir() / "whisper-large-v3"


def nllb_dir() -> Path:
    return paths.models_dir() / "nllb-200-distilled-600M-ct2"


def _say(progress: Progress, msg: str) -> None:
    if progress:
        progress(msg)
    else:
        print(msg, flush=True)


def whisper_ready() -> bool:
    return (whisper_dir() / "model.bin").is_file()


def nllb_ready() -> bool:
    d = nllb_dir()
    return (d / "model.bin").is_file() and (d / "sentencepiece.bpe.model").is_file()


def models_ready() -> bool:
    return whisper_ready() and nllb_ready()


def ensure_whisper(progress: Progress = None) -> Path:
    out = whisper_dir()
    if whisper_ready():
        return out
    from faster_whisper.utils import download_model

    _say(progress, "Downloading Whisper large-v3 (~3 GB, one time)...")
    download_model(WHISPER_REPO, output_dir=str(out))
    _say(progress, "Whisper large-v3 ready.")
    return out


def ensure_nllb(progress: Progress = None) -> Path:
    out = nllb_dir()
    if nllb_ready():
        return out
    try:
        from ctranslate2.converters import TransformersConverter
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("ctranslate2 is not installed") from e

    _say(progress, "Downloading NLLB-200 (~2.5 GB) and converting to CTranslate2 int8 (one time)...")
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    TransformersConverter(NLLB_REPO, copy_files=NLLB_TOKENIZER_FILES).convert(
        str(tmp), quantization="int8_float16", force=True
    )
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    _say(progress, "NLLB ready.")
    return out


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def main() -> None:
    ensure_whisper()
    ensure_nllb()
    print(f"Models are in {paths.models_dir()}")
    print(f"CUDA available: {cuda_available()}")


if __name__ == "__main__":
    main()
