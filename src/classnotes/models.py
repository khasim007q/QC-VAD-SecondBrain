"""Download Whisper and download + convert NLLB (one-time setup).

Run directly to set everything up:  uv run python -m classnotes.models
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from . import paths

# Names faster-whisper resolves to Hugging Face repos, with their download size.
WHISPER_MODELS = {"large-v3-turbo": "~1.6 GB", "large-v3": "~3 GB"}
DEFAULT_WHISPER = "large-v3-turbo"
NLLB_REPO = "facebook/nllb-200-distilled-600M"
NLLB_TOKENIZER_FILES = [
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]

Progress = Callable[[str], None] | None


def whisper_dir(name: str = DEFAULT_WHISPER) -> Path:
    if name not in WHISPER_MODELS:
        raise ValueError(f"unknown Whisper model {name!r}")
    return paths.models_dir() / f"whisper-{name}"


def nllb_dir() -> Path:
    return paths.models_dir() / "nllb-200-distilled-600M-ct2"


def _say(progress: Progress, msg: str) -> None:
    if progress:
        progress(msg)
    else:
        print(msg, flush=True)


def whisper_ready(name: str = DEFAULT_WHISPER) -> bool:
    d = whisper_dir(name)
    return all((d / f).is_file() for f in ("model.bin", "config.json", "tokenizer.json",
                                            "preprocessor_config.json"))


def nllb_ready() -> bool:
    d = nllb_dir()
    return (d / "model.bin").is_file() and (d / "sentencepiece.bpe.model").is_file()


def models_ready(name: str = DEFAULT_WHISPER) -> bool:
    return whisper_ready(name) and nllb_ready()


def ensure_whisper(progress: Progress = None, name: str = DEFAULT_WHISPER) -> Path:
    out = whisper_dir(name)
    if whisper_ready(name):
        return out
    from faster_whisper.utils import download_model

    _say(progress, f"Downloading Whisper {name} ({WHISPER_MODELS[name]}, one time)...")
    download_model(name, output_dir=str(out))
    _say(progress, f"Whisper {name} ready.")
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


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_active: list[subprocess.Popen] = []
_active_lock = threading.Lock()


def run_tracked(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a helper process that kill_active() can stop (e.g. when the app closes)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    with _active_lock:
        _active.append(proc)
    try:
        out, err = proc.communicate()
    finally:
        with _active_lock:
            _active.remove(proc)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def kill_active() -> None:
    """Stop helper processes, including their children (uv starts python as a child)."""
    with _active_lock:
        procs = list(_active)
    for p in procs:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                               capture_output=True, creationflags=_NO_WINDOW)
            else:
                p.kill()
        except OSError:
            pass


def ensure_nllb(progress: Progress = None) -> Path:
    out = nllb_dir()
    if nllb_ready():
        return out

    _say(progress, "Downloading NLLB-200 (~2.5 GB) and converting to CTranslate2 int8 (one time)...")
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    proc = run_tracked(convert_command(NLLB_REPO, tmp))
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
