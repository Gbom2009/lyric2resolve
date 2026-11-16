"""Instrumental stem (song minus aligned acapella) and the optional separation fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

STEM_VERSION = 1  # bump to invalidate cached stems when the algorithm changes


@dataclass
class SubtractResult:
    instrumental: np.ndarray
    gain: list[float]          # per channel, applied to the acapella
    residual_ratio: float      # energy(instrumental) / energy(song); low = acapella explained much


def subtract_vocals(song: np.ndarray, acapella: np.ndarray) -> SubtractResult:
    """instrumental = song - g * acapella, with least-squares gain per channel (clamped 0..2).

    Both inputs (samples, channels), already aligned and the same length. Works when the acapella
    is the official stem of the same master; otherwise the result is a rough approximation.
    """
    n = min(len(song), len(acapella))
    s = song[:n].astype(np.float64)
    v = acapella[:n].astype(np.float64)
    if v.shape[1] != s.shape[1]:
        v = np.repeat(v.mean(axis=1, keepdims=True), s.shape[1], axis=1)
    gains = []
    out = np.empty_like(s)
    for ch in range(s.shape[1]):
        vv = float(np.dot(v[:, ch], v[:, ch]))
        g = float(np.dot(s[:, ch], v[:, ch]) / vv) if vv > 0 else 0.0
        g = min(max(g, 0.0), 2.0)
        gains.append(g)
        out[:, ch] = s[:, ch] - g * v[:, ch]
    es = float(np.sum(s ** 2))
    ratio = float(np.sum(out ** 2) / es) if es > 0 else 0.0
    if len(song) > n:  # keep the song's tail (acapella ended earlier)
        out = np.concatenate([out, song[n:].astype(np.float64)])
    return SubtractResult(out.astype(np.float32), gains, ratio)


# ------------------------------------------------------------------ separation fallback
class Separator(Protocol):
    name: str

    def separate(self, song_wav: Path, out_dir: Path) -> tuple[Path, Path]:
        """Return (vocals_wav, instrumental_wav)."""


class AudioSeparatorBackend:
    """python-audio-separator (BS-Roformer by default; MDX23C as an alternative model)."""

    name = "audio-separator"
    DEFAULT_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"  # verify name on the PC (verify_local)

    def __init__(self, model: str | None = None, model_dir: Path | None = None):
        self.model = model or self.DEFAULT_MODEL
        self.model_dir = model_dir

    def separate(self, song_wav: Path, out_dir: Path) -> tuple[Path, Path]:
        from audio_separator.separator import Separator as _Sep  # heavy import, PC only

        out_dir.mkdir(parents=True, exist_ok=True)
        kwargs = {"output_dir": str(out_dir)}
        if self.model_dir:
            kwargs["model_file_dir"] = str(self.model_dir)
        sep = _Sep(**kwargs)
        sep.load_model(model_filename=self.model)
        files = [out_dir / Path(f).name for f in sep.separate(str(song_wav))]
        return pick_stems(files)


class DemucsBackend:
    """Backup: Demucs htdemucs_ft, two-stem mode."""

    name = "demucs"

    def separate(self, song_wav: Path, out_dir: Path) -> tuple[Path, Path]:
        import importlib.util
        import subprocess
        import sys

        if importlib.util.find_spec("demucs") is None:
            # Not installed by setup: Demucs 4 needs torchaudio < 2.1, which conflicts with current PyTorch.
            raise RuntimeError("not installed (optional backup)")
        cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs_ft", "--two-stems", "vocals", "-o", str(out_dir),
               str(song_wav)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0:
            raise RuntimeError(f"exit {proc.returncode}: " + (proc.stderr or proc.stdout).strip()[-400:])
        return pick_stems(list(out_dir.rglob("*.wav")))


def pick_stems(files: list[Path]) -> tuple[Path, Path]:
    vocals = [f for f in files if "vocal" in f.name.lower() and "no_vocal" not in f.name.lower()
              and "no-vocal" not in f.name.lower()]
    inst = [f for f in files if any(k in f.name.lower() for k in ("instrumental", "no_vocals", "no-vocals",
                                                                   "accompaniment"))]
    if not vocals or not inst:
        raise RuntimeError(f"Separation output not recognised: {[f.name for f in files]}")
    return vocals[0], inst[0]


def separate_cached(song_wav: Path, song_hash: str, cache_dir: Path,
                    backends: list[Separator]) -> tuple[Path, Path, str]:
    """Try backends in order; cache per song hash. Returns (vocals, instrumental, backend name)."""
    stem_dir = cache_dir / "stems" / f"{song_hash}-v{STEM_VERSION}"
    meta = stem_dir / "stems.json"
    if meta.exists():
        info = json.loads(meta.read_text(encoding="utf-8"))
        v, i = stem_dir / info["vocals"], stem_dir / info["instrumental"]
        if v.exists() and i.exists():
            return v, i, info["backend"]
    errors = []
    for backend in backends:
        try:
            v, i = backend.separate(song_wav, stem_dir / backend.name)
        except Exception as exc:  # noqa: BLE001 - try the next backend
            errors.append(f"{backend.name}: {exc}")
            continue
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"vocals": str(v.relative_to(stem_dir)),
                                    "instrumental": str(i.relative_to(stem_dir)),
                                    "backend": backend.name}), encoding="utf-8")
        return v, i, backend.name
    raise RuntimeError("Vocal separation failed:\n" + "\n".join(errors) + "\nTip: upload the acapella too "
                       "(the best result anyway), or run the launcher's Update / setup_windows.bat to (re)install "
                       "the separation packages.")
