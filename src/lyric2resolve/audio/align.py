"""A/B alignment: estimate the offset between the full song (A) and the acapella (B).

Cross-correlation on band-limited, decimated mono signals (FFT based), refined with
parabolic interpolation. Convention: offset_ms > 0 means the acapella starts LATER
than the vocals in the song (acapella has extra silence at the start).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ANALYSIS_SR = 11025  # 44100 / 4 -> ~0.09 ms per sample, plenty for frame accuracy
WARN_MS = 5.0         # below this an offset is inaudible/irrelevant (< 1/8 frame at 25 fps)


@dataclass
class OffsetResult:
    offset_ms: float
    confidence: float  # normalised correlation peak 0..1
    max_lag_ms: float

    @property
    def significant(self) -> bool:
        return abs(self.offset_ms) >= WARN_MS

    @property
    def reliable(self) -> bool:
        return self.confidence >= 0.2

    def message(self) -> str:
        if not self.reliable:
            return (f"Could not reliably match the acapella to the song (confidence {self.confidence:.2f}). "
                    "Check that the acapella belongs to this exact version of the song.")
        if not self.significant:
            return f"Acapella and song are aligned (offset {self.offset_ms:+.1f} ms)."
        later = "later" if self.offset_ms > 0 else "earlier"
        return (f"WARNING: the acapella starts {abs(self.offset_ms):.1f} ms {later} than the vocals in the song. "
                "Use auto-compensate to fix the timing.")


def _prepare(x: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import resample_poly

    x = x.mean(axis=1) if x.ndim == 2 else x
    x = x.astype(np.float64)
    if sr != ANALYSIS_SR:
        g = np.gcd(int(sr), ANALYSIS_SR)
        x = resample_poly(x, ANALYSIS_SR // g, int(sr) // g)
    x = x - x.mean()
    return x


def estimate_offset(song: np.ndarray, acapella: np.ndarray, sr: int, max_lag_s: float = 10.0,
                    analysis_s: float | None = 120.0) -> OffsetResult:
    """analysis_s limits how much audio is correlated (speed); None = everything."""
    from scipy.signal import correlate

    a, b = _prepare(song, sr), _prepare(acapella, sr)
    if analysis_s:
        n = int(analysis_s * ANALYSIS_SR)
        a, b = a[:n], b[:n]
    if not len(a) or not len(b) or not np.any(b) or not np.any(a):
        return OffsetResult(0.0, 0.0, max_lag_s * 1000)
    corr = correlate(b, a, mode="full", method="fft")  # index k -> lag k - (len(a) - 1)
    lags = np.arange(-(len(a) - 1), len(b))
    max_lag = int(max_lag_s * ANALYSIS_SR)
    window = (lags >= -max_lag) & (lags <= max_lag)
    idx_in = np.argmax(np.abs(corr[window]))
    idx = np.flatnonzero(window)[idx_in]
    # parabolic refinement for sub-sample precision
    shift = 0.0
    if 0 < idx < len(corr) - 1:
        y0, y1, y2 = np.abs(corr[idx - 1:idx + 2])
        denom = y0 - 2 * y1 + y2
        if denom != 0:
            shift = 0.5 * (y0 - y2) / denom
    lag = lags[idx] + shift
    # confidence: correlation normalised by the energy of the overlapping parts
    lag_i = int(round(lags[idx]))
    if lag_i >= 0:
        aa, bb = a[: len(b) - lag_i], b[lag_i:]
    else:
        aa, bb = a[-lag_i:], b[: len(a) + lag_i]
    m = min(len(aa), len(bb))
    denom = np.sqrt(np.sum(aa[:m] ** 2) * np.sum(bb[:m] ** 2))
    conf = float(abs(np.dot(aa[:m], bb[:m])) / denom) if denom > 0 else 0.0
    return OffsetResult(float(lag / ANALYSIS_SR * 1000.0), conf, max_lag_s * 1000)


def compensate(acapella: np.ndarray, sr: int, offset_ms: float, length: int | None = None) -> np.ndarray:
    """Shift the acapella so it lines up with the song (remove leading audio if it starts later)."""
    shift = int(round(offset_ms / 1000.0 * sr))
    x = acapella if acapella.ndim == 2 else acapella[:, None]
    if shift > 0:
        x = x[shift:]
    elif shift < 0:
        x = np.concatenate([np.zeros((-shift, x.shape[1]), dtype=x.dtype), x])
    if length is not None:
        if len(x) < length:
            x = np.concatenate([x, np.zeros((length - len(x), x.shape[1]), dtype=x.dtype)])
        x = x[:length]
    return x if acapella.ndim == 2 else x[:, 0]
