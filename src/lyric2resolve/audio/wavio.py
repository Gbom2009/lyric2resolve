"""Read/write wav as float32 arrays shaped (samples, channels)."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return data, sr


def write(path: Path, data: np.ndarray, sr: int) -> Path:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(data, -1.0, 1.0), sr, subtype="PCM_16")
    return path


def mono(data: np.ndarray) -> np.ndarray:
    return data.mean(axis=1) if data.ndim == 2 else data
