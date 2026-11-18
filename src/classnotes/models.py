"""Download Whisper and download + convert NLLB (one-time setup).

Run directly to set everything up:  uv run python -m classnotes.models
"""

from __future__ import annotations

import os
import shutil
import subprocess
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


_CONVERT_SCRIPT = """
import sys
from ctranslate2.converters import TransformersConverter
repo, out, files = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
TransformersConverter(repo, copy_files=files).convert(out, quantization="int8_float16", force=True)
"""

CONVERT_DEPS = ["ctranslate2>=4.5", "transformers>=4.40", "torch", "sentencepiece"]


def _uv() -> str:
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is needed once to convert the NLLB model: https://docs.astral.sh/uv/")
    return uv


def convert_command(repo: str, out: Path) -> list[str]:
    """One-time conversion runs in a throwaway uv environment, so torch (~1 GB) is never
    part of the app's own environment."""
    cmd = [_uv(), "run", "--no-project", "--quiet", "--python", "3.12"]
    for dep in CONVERT_DEPS:
        cmd += ["--with", dep]
    return cmd + ["python", "-c", _CONVERT_SCRIPT, repo, str(out), ",".join(NLLB_TOKENIZER_FILES)]


def ensure_nllb(progress: Progress = None) -> Path:
    out = nllb_dir()
    if nllb_ready():
        return out

    _say(progress, "Downloading NLLB-200 (~2.5 GB) and converting to CTranslate2 int8 (one time)...")
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    proc = subprocess.run(
        convert_command(NLLB_REPO, tmp),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0 or not (tmp / "model.bin").is_file():
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-15:])
        raise RuntimeError(f"NLLB conversion failed:\n{tail}")
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
