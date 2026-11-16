"""Music analysis with librosa: BPM, beats, downbeats, key, energy curve, sections.

madmom is not used (unmaintained, hard to install on Windows/Python 3.12); all results
are estimates the user can edit in the editor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

ANALYSIS_SR = 22050
HOP = 512
BEAT_HOP = 256  # finer tempo resolution: at hop 512, 120 BPM is not representable (117.5 / 123.0)
ENERGY_RATE = 10.0  # energy curve samples per second

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class MusicAnalysis:
    duration: float
    bpm: float
    beats: list[float]
    downbeats: list[float]
    key: str
    key_confidence: float
    energy: list[float]                       # 0..1 at ENERGY_RATE Hz
    energy_rate: float = ENERGY_RATE
    sections: list[dict] = field(default_factory=list)  # {label, start, end, energy}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bpm"] = round(self.bpm, 2)
        return d


def to_mono(y: np.ndarray, sr: int) -> np.ndarray:
    import librosa

    y = y.mean(axis=1) if y.ndim == 2 else y
    y = y.astype(np.float32)
    return librosa.resample(y, orig_sr=sr, target_sr=ANALYSIS_SR) if sr != ANALYSIS_SR else y


def estimate_key(y: np.ndarray, sr: int = ANALYSIS_SR) -> tuple[str, float]:
    """Krumhansl-Schmuckler key profile correlation on mean chroma."""
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP).mean(axis=1)
    if not np.any(chroma):
        return "unknown", 0.0
    scores = []
    for mode, prof in (("major", MAJOR), ("minor", MINOR)):
        for tonic in range(12):
            r = np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]
            scores.append((r, f"{NOTES[tonic]} {mode}"))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    return best[1], float(max(0.0, best[0] - second[0]) + max(0.0, best[0])) / 2


def fit_period(beats: np.ndarray) -> float:
    """Beat period from a least-squares fit of beat time vs beat number (robust to frame quantisation)."""
    beats = np.asarray(beats, dtype=float)
    p0 = float(np.median(np.diff(beats)))
    if len(beats) < 4 or p0 <= 0:
        return p0
    idx = np.round((beats - beats[0]) / p0)
    slope = float(np.polyfit(idx, beats, 1)[0])
    return slope if 0.5 * p0 < slope < 2 * p0 else p0


def extend_grid(beats: np.ndarray, duration: float, max_gap_factor: float = 1.6) -> np.ndarray:
    """Fill the start, end and long holes of a beat list with the median beat period.

    Quiet intros/breakdowns often get no tracked beats; a constant grid is what DJs and
    editors expect for (electronic) music.
    """
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 2:
        return beats
    period = fit_period(beats)
    out = list(np.arange(beats[0] - period, -1e-6, -period)[::-1])
    for a, b in zip(beats, beats[1:]):
        out.append(a)
        if b - a > max_gap_factor * period:
            n = int(round((b - a) / period))
            out.extend(a + (b - a) * k / n for k in range(1, n))
    out.append(beats[-1])
    out.extend(np.arange(beats[-1] + period, duration - 1e-6, period))
    return np.array(out)


def estimate_downbeats(beats: np.ndarray, onset_env: np.ndarray, sr: int, beats_per_bar: int = 4) -> np.ndarray:
    """Pick the beat phase whose beats carry the strongest low-frequency onsets."""
    if len(beats) < beats_per_bar:
        return beats[:1]
    frames = np.clip(np.round(beats * sr / HOP).astype(int), 0, len(onset_env) - 1)
    # local max around each beat (+-2 frames) tolerates small beat-tracking offsets
    strength = np.array([onset_env[max(0, f - 2):f + 3].max() for f in frames])
    phase = int(np.argmax([strength[k::beats_per_bar].mean() for k in range(beats_per_bar)]))
    return beats[phase::beats_per_bar]


def energy_curve(y: np.ndarray, sr: int = ANALYSIS_SR, rate: float = ENERGY_RATE) -> np.ndarray:
    import librosa

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    t_src = np.arange(len(rms)) * HOP / sr
    t_dst = np.arange(0, len(y) / sr, 1.0 / rate)
    e = np.interp(t_dst, t_src, rms)
    k = max(1, int(rate))  # 1 s moving average
    e = np.convolve(e, np.ones(k) / k, mode="same")
    peak = np.percentile(e, 98) if len(e) else 0
    return np.clip(e / peak, 0, 1) if peak > 0 else np.zeros_like(e)


def find_boundaries(y: np.ndarray, sr: int, beats: np.ndarray, min_section_s: float = 12.0) -> list[float]:
    """Checkerboard novelty on a beat-synchronous self-similarity matrix of chroma + MFCC + RMS."""
    import librosa
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks

    if len(beats) < 16:
        return []
    frames = librosa.time_to_frames(beats, sr=sr, hop_length=HOP)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=13)
    rms = librosa.feature.rms(y=y, hop_length=HOP)
    feats = np.vstack([librosa.util.normalize(chroma, axis=0), librosa.util.normalize(mfcc, axis=1),
                       3 * rms / (rms.max() or 1)])
    sync = librosa.util.sync(feats, frames, aggregate=np.median)
    sync = sync / (np.linalg.norm(sync, axis=0, keepdims=True) + 1e-9)
    ssm = sync.T @ sync
    n = ssm.shape[0]
    w = 8  # beats (2 bars) on each side
    kernel = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((w, w)))
    g = np.outer(np.hanning(2 * w), np.hanning(2 * w))
    kernel = kernel * g
    padded = np.pad(ssm, w, mode="edge")
    novelty = np.array([np.sum(padded[i:i + 2 * w, i:i + 2 * w] * kernel) for i in range(n)])
    novelty = gaussian_filter1d(np.maximum(novelty, 0), 1)
    if novelty.max() <= 0:
        return []
    beat_period = float(np.median(np.diff(beats)))
    min_dist = max(4, int(min_section_s / beat_period))
    peaks, _ = find_peaks(novelty / novelty.max(), distance=min_dist, height=0.15)
    times = [float(beats[min(p, len(beats) - 1)]) for p in peaks]
    return [t for t in times if t > min_section_s / 2]


def label_sections(bounds: list[float], duration: float, energy: np.ndarray, rate: float) -> list[dict]:
    edges = [0.0] + sorted(bounds) + [duration]
    secs = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 1.0:
            continue
        seg = energy[int(a * rate):max(int(a * rate) + 1, int(b * rate))]
        secs.append({"start": round(a, 3), "end": round(b, 3), "energy": float(seg.mean()) if len(seg) else 0.0})
    if not secs:
        return []
    levels = np.array([s["energy"] for s in secs])
    hi = np.percentile(levels, 66) if len(levels) > 2 else levels.max()
    for i, s in enumerate(secs):
        if i == 0 and len(secs) > 2 and s["energy"] < hi:
            s["label"] = "intro"
        elif i == len(secs) - 1 and len(secs) > 2 and s["energy"] < hi:
            s["label"] = "outro"
        elif s["energy"] >= hi:
            s["label"] = "chorus"
        else:
            s["label"] = "verse"
    return secs


def analyze(y: np.ndarray, sr: int) -> MusicAnalysis:
    import librosa

    m = to_mono(y, sr)
    duration = len(m) / ANALYSIS_SR
    onset_env = librosa.onset.onset_strength(y=m, sr=ANALYSIS_SR, hop_length=BEAT_HOP)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=ANALYSIS_SR, hop_length=BEAT_HOP, units="time",
                                             trim=False)
    beats = extend_grid(np.asarray(beats), duration)
    bpm = 60.0 / fit_period(beats) if len(beats) > 3 else float(np.atleast_1d(tempo)[0])
    # low-band (< ~200 Hz) linear energy: bar starts usually carry the strongest kick/bass
    S = np.abs(librosa.stft(m, hop_length=HOP))
    low = S[:20].sum(axis=0)
    downbeats = estimate_downbeats(np.asarray(beats), low, ANALYSIS_SR)
    key, key_conf = estimate_key(m)
    energy = energy_curve(m)
    bounds = find_boundaries(m, ANALYSIS_SR, np.asarray(beats))
    return MusicAnalysis(round(duration, 3), bpm, [round(float(b), 3) for b in beats],
                         [round(float(b), 3) for b in downbeats], key, round(key_conf, 3),
                         [round(float(e), 3) for e in energy], ENERGY_RATE,
                         label_sections(bounds, duration, energy, ENERGY_RATE))
