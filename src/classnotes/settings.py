"""User settings, saved as JSON in the app data folder."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from . import paths
from .translate import DEFAULT_TERMS

# Passed to Whisper as initial_prompt: biases it toward these spellings.
DEFAULT_GLOSSARY = (
    "قرآن، سورۃ، آیت، تفسیر، تجوید، حدیث، اللہ تعالیٰ، رسول اللہ ﷺ، صحابہ، حضرت ابو بکر صدیق، "
    "ہجرت، مکہ، مدینہ، قریش، مشرکین، مہاجر، انصار، قتل، قریب، نماز ظہر، نعوذ باللہ، "
    "Quran, Surah, ayah, tafseer, tajweed, hadith"
)


def _default_library() -> str:
    return str(paths.default_library_dir())


@dataclass
class Settings:
    glossary: str = DEFAULT_GLOSSARY
    terms: str = DEFAULT_TERMS
    min_silence_ms: int = 500
    max_speech_s: float = 20.0
    min_conf: float = 0.7
    min_dur_s: float = 1.5
    merge_gap_s: float = 1.0
    merge_max_s: float = 25.0
    device: str = "auto"  # "auto" | "cuda" | "cpu"
    whisper_model: str = "large-v3-turbo"  # or "large-v3": ~2-3x slower, the original model
    batch_size: int = 8  # blocks per GPU pass (halved automatically if the GPU runs out of memory)
    library_dir: str = field(default_factory=_default_library)

    @staticmethod
    def path():
        return paths.data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), "utf-8")

    def resolved_device(self) -> str:
        if self.device in ("cuda", "cpu"):
            return self.device
        from .models import cuda_available

        return "cuda" if cuda_available() else "cpu"
