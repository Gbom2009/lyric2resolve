"""Audio-reactive curves: band energies (bass / mids / highs), RMS, onset strength and beat pulses,
sampled exactly at the project frame rate, smoothed with attack/release, gain + normalisation.

Curves are stored as JSON (and CSV) next to the .blend so they can be re-tuned without re-analysing.
Pure numpy (librosa only for the onset envelope when available).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Band:
    name: str
    low_hz: float
    high_hz: float
    gain: float = 1.0
    attack_ms: float = 15.0
    release_ms: float = 180.0


DEFAULT_BANDS = [Band("bass", 20, 150, 1.0, 10, 220), Band("mids", 150, 2000, 1.0, 20, 180),
                 Band("highs", 2000, 12000, 1.0, 5, 120)]


@dataclass
class CurveConfig:
    fps: float = 25.0
    bands: list[Band] = field(default_factory=lambda: [Band(**asdict(b)) for b in DEFAULT_BANDS])
    rms_attack_ms: float = 20.0
    rms_release_ms: float = 250.0
    onset_release_ms: float = 120.0
    beat_decay_ms: float = 180.0
    normalize_percentile: float = 98.0   # this percentile maps to 1.0 (peaks above clip at 1.0)
    floor: float = 0.0                   # values below are set to 0 (noise gate after normalising)

    @classmethod
    def from_dict(cls, d: dict) -> "CurveConfig":
        d = dict(d or {})
        bands = [Band(**b) for b in d.pop("bands", [])] or [Band(**asdict(b)) for b in DEFAULT_BANDS]
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(bands=bands, **known)


@dataclass
class Curves:
    fps: float
    frames: int
    data: dict[str, list[float]]
    config: dict

    def to_json(self) -> str:
        return json.dumps({"fps": self.fps, "frames": self.frames, "config": self.config,
                           "curves": {k: [round(float(x), 4) for x in v] for k, v in self.data.items()}})

    def save(self, folder: Path, stem: str = "curves") -> tuple[Path, Path]:
        folder.mkdir(parents=True, exist_ok=True)
        js, cs = folder / f"{stem}.json", folder / f"{stem}.csv"
        js.write_text(self.to_json(), encoding="utf-8")
        with open(cs, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            names = list(self.data)
            w.writerow(["frame", "time_s", *names])
            for i in range(self.frames):
                w.writerow([i, f"{i / self.fps:.4f}", *(f"{self.data[n][i]:.4f}" for n in names)])
        return js, cs

    @classmethod
    def load(cls, path: Path) -> "Curves":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["fps"], d["frames"], d["curves"], d.get("config", {}))


def envelope(x: np.ndarray, fps: float, attack_ms: float, release_ms: float) -> np.ndarray:
    """One-pole attack/release follower in the frame domain."""
    a_att = 1.0 - math.exp(-1.0 / max(1e-6, attack_ms / 1000.0 * fps)) if attack_ms > 0 else 1.0
    a_rel = 1.0 - math.exp(-1.0 / max(1e-6, release_ms / 1000.0 * fps)) if release_ms > 0 else 1.0
    y = np.empty_like(x, dtype=np.float64)
    prev = 0.0
    for i, v in enumerate(x):
        prev += (v - prev) * (a_att if v > prev else a_rel)
        y[i] = prev
    return y


def normalize(x: np.ndarray, percentile: float, floor: float = 0.0) -> np.ndarray:
    ref = np.percentile(x, percentile) if len(x) else 0.0
    if ref <= 1e-12:
        return np.zeros_like(x)
    y = np.clip(x / ref, 0.0, 1.0)
    if floor > 0:
        y = np.where(y < floor, 0.0, (y - floor) / (1 - floor))
    return y


def frame_spectra(y: np.ndarray, sr: int, fps: float, n_fft: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude spectra centred on every video frame (frame i at time i/fps)."""
    mono = y.mean(axis=1) if y.ndim == 2 else y
    frames = int(math.floor(len(mono) / sr * fps))
    win = np.hanning(n_fft)
    pad = np.concatenate([np.zeros(n_fft // 2), mono.astype(np.float64), np.zeros(n_fft)])
    centers = (np.arange(frames) / fps * sr).astype(np.int64)
    idx = centers[:, None] + np.arange(n_fft)[None, :]
    spec = np.abs(np.fft.rfft(pad[idx] * win, axis=1))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return spec, freqs


def beat_pulses(beats_s: list[float], frames: int, fps: float, decay_ms: float) -> np.ndarray:
    out = np.zeros(frames)
    tau = max(1e-6, decay_ms / 1000.0 * fps)
    for b in beats_s or []:
        f0 = int(round(b * fps))
        if 0 <= f0 < frames:
            n = np.arange(frames - f0)
            out[f0:] = np.maximum(out[f0:], np.exp(-n / tau))
    return out


def compute(y: np.ndarray, sr: int, cfg: CurveConfig, beats_s: list[float] | None = None) -> Curves:
    spec, freqs = frame_spectra(y, sr, cfg.fps)
    frames = spec.shape[0]
    data: dict[str, list[float]] = {}
    power = spec ** 2
    for b in cfg.bands:
        sel = (freqs >= b.low_hz) & (freqs < b.high_hz)
        raw = np.sqrt(power[:, sel].mean(axis=1)) if sel.any() else np.zeros(frames)
        env = envelope(raw * b.gain, cfg.fps, b.attack_ms, b.release_ms)
        data[b.name] = list(normalize(env, cfg.normalize_percentile, cfg.floor))
    rms = np.sqrt(power.mean(axis=1))
    data["rms"] = list(normalize(envelope(rms, cfg.fps, cfg.rms_attack_ms, cfg.rms_release_ms),
                                 cfg.normalize_percentile, cfg.floor))
    flux = np.maximum(0.0, np.diff(np.log1p(spec), axis=0, prepend=np.log1p(spec[:1]))).sum(axis=1)
    data["onset"] = list(normalize(envelope(flux, cfg.fps, 0.0, cfg.onset_release_ms), cfg.normalize_percentile))
    data["beat"] = list(beat_pulses(beats_s or [], frames, cfg.fps, cfg.beat_decay_ms))
    return Curves(cfg.fps, frames, data, asdict(cfg))


def section_intensity(sections: list[dict], frames: int, fps: float, levels: dict[str, float] | None = None,
                      fade_s: float = 1.0) -> list[float]:
    """Per-frame intensity multiplier from section labels (e.g. chorus/drop brighter), smoothly faded."""
    levels = levels or {"intro": 0.5, "verse": 0.7, "pre-chorus": 0.85, "chorus": 1.0, "drop": 1.0,
                        "bridge": 0.6, "breakdown": 0.45, "outro": 0.5}
    out = np.full(frames, 0.7)
    for s in sections:
        a, b = int(s["start"] * fps), int(s["end"] * fps)
        out[max(0, a):min(frames, b)] = levels.get(str(s.get("label", "")).lower(), 0.7)
    k = max(1, int(fade_s * fps))
    smooth = np.convolve(np.pad(out, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    return [round(float(x), 4) for x in smooth[:frames]]
