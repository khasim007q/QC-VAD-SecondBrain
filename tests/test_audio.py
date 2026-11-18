import wave

import numpy as np
import pytest

from classnotes.asr import AudioError, load_audio


def _write_wav(path, seconds=2.0, sr=22050):
    t = np.arange(int(seconds * sr)) / sr
    data = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(data.tobytes())


def test_load_audio_resamples_to_16k(tmp_path):
    p = tmp_path / "tone.wav"
    _write_wav(p)
    audio = load_audio(p)
    assert audio.dtype == np.float32
    assert abs(len(audio) - 32000) < 400


def test_load_audio_corrupt_file(tmp_path):
    p = tmp_path / "bad.mp3"
    p.write_bytes(b"not audio at all")
    with pytest.raises(AudioError):
        load_audio(p)


def test_load_audio_missing_file(tmp_path):
    with pytest.raises(AudioError, match="not found"):
        load_audio(tmp_path / "nope.m4a")
