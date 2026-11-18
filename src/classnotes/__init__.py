"""Class Notes: Urdu/English class recordings -> English translation notes."""

import os
import sys
from pathlib import Path


def _register_nvidia_dlls() -> None:
    """Make pip-installed CUDA libraries (cuBLAS, cuDNN) visible to CTranslate2 on Windows."""
    if sys.platform != "win32":
        return
    for base in map(Path, sys.path):
        nvidia = base / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in nvidia.glob("*/bin"):
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                continue
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dlls()
