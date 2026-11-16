"""Whisper engines behind one small interface.

Default: stable-ts wrapping faster-whisper (large-v3, CUDA float16). Real models are
only loaded on the user's PC; tests use FakeEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TranscriptWord:
    text: str
    start: float
    end: float
    confidence: float
    segment: int


@dataclass
class Transcript:
    words: list[TranscriptWord]
    language: str
    mode: str                     # "transcribe" | "align"
    params: dict = field(default_factory=dict)


@dataclass
class EngineOptions:
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str | None = None   # None = auto-detect
    vad: bool = True
    vad_threshold: float = 0.35   # singing scores lower than speech in Silero VAD (default 0.5 drops sung lines)
    model_dir: str | None = None  # download/cache folder (data/models/whisper)
    backend: str = "faster-whisper"   # faster-whisper (CTranslate2: NVIDIA/CPU) | mlx (Apple Silicon M chips)


class Engine(Protocol):
    def transcribe(self, audio_path: str) -> Transcript: ...

    def align(self, audio_path: str, lyrics: str) -> Transcript: ...


def words_from_result(result: Any) -> list[TranscriptWord]:
    """Convert a stable-ts WhisperResult (segments[].words[] with word/start/end/probability)."""
    out: list[TranscriptWord] = []
    for si, seg in enumerate(getattr(result, "segments", []) or []):
        for w in getattr(seg, "words", []) or []:
            text = (getattr(w, "word", "") or "").strip()
            if not text:
                continue
            prob = getattr(w, "probability", None)
            out.append(TranscriptWord(text, float(w.start), float(w.end),
                                      1.0 if prob is None else float(prob), si))
    return out


CUDA12_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")
_GPU_LIB_ERROR = ("cublas", "cudnn", "cudart", "cuda driver", "cuda failed", "no cuda", "cannot be loaded",
                  "not found or cannot")


def cuda_dll_dirs(site_dirs: list[str] | None = None) -> list[str]:
    """Folders with NVIDIA DLLs that faster-whisper's CTranslate2 needs on Windows (cuBLAS 12, cuDNN 9):
    torch's own lib folder (CUDA 12 builds ship cublas64_12.dll + cuDNN 9) and pip 'nvidia-*' wheels."""
    import glob
    import os
    import site
    import sys

    if site_dirs is None:
        site_dirs = [p for p in (site.getsitepackages() if hasattr(site, "getsitepackages") else []) + sys.path
                     if p and p.lower().endswith("site-packages")]
    out: list[str] = []
    for sp in dict.fromkeys(site_dirs):
        for cand in [os.path.join(sp, "torch", "lib")] + sorted(glob.glob(os.path.join(sp, "nvidia", "*", "bin"))):
            if os.path.isdir(cand) and cand not in out:
                out.append(cand)
    return out


def add_cuda_dll_dirs(platform: str | None = None) -> list[str]:
    """Windows: make those DLLs findable (CTranslate2 loads cublas64_12.dll by name via PATH)."""
    import os
    import sys

    if not (platform or sys.platform).startswith("win"):
        return []
    dirs = cuda_dll_dirs()
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass
    path = os.environ.get("PATH", "")
    missing = [d for d in dirs if d.lower() not in path.lower()]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing + [path])
    return dirs


def is_gpu_library_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _GPU_LIB_ERROR)


class StableTsEngine:
    """stable-ts + faster-whisper. Loads the model lazily on first use.

    If the GPU libraries cannot be loaded, it falls back to the CPU (slow but working) and records why in
    `fallback_reason` so the app can tell the user."""

    def __init__(self, options: EngineOptions | None = None):
        self.opt = options or EngineOptions()
        self._model = None
        self.fallback_reason = ""

    def _load(self, device: str, compute_type: str):
        import stable_whisper  # heavy, PC only

        if self.opt.backend == "mlx":
            import os

            if self.opt.model_dir:  # MLX models come from Hugging Face; keep them in the app's models folder
                os.environ.setdefault("HF_HUB_CACHE", self.opt.model_dir)
            return stable_whisper.load_mlx_whisper(self.opt.model)
        kwargs = {"device": device, "compute_type": compute_type}
        if self.opt.model_dir:
            kwargs["download_root"] = self.opt.model_dir
        return stable_whisper.load_faster_whisper(self.opt.model, **kwargs)

    def model(self):
        if self._model is None:
            if self.opt.backend == "mlx":
                try:
                    self._model = self._load("mps", "float16")
                except Exception as exc:  # no MLX / model problem: CPU engine instead of failing
                    self._mlx_fallback(exc)
                return self._model
            if self.opt.device == "cuda":
                add_cuda_dll_dirs()
            self._model = self._load(self.opt.device, self.opt.compute_type)
        return self._model

    def _mlx_fallback(self, exc: BaseException) -> None:
        self.fallback_reason = (f"MLX Whisper could not be used ({exc}); Whisper ran on the CPU instead (slower). "
                                "Run the launcher's Run setup / setup_mac.command to (re)install mlx-whisper.")
        self.opt.backend, self.opt.device, self.opt.compute_type = "faster-whisper", "cpu", "int8"
        self._model = self._load("cpu", "int8")

    def close(self) -> None:
        """Free the model's memory (8 GB Macs: before Blender starts)."""
        self._model = None
        import gc

        gc.collect()
        if self.opt.backend == "mlx":
            try:
                import mlx.core as mx

                (getattr(mx, "clear_cache", None) or mx.metal.clear_cache)()
            except Exception:  # noqa: BLE001 - best effort
                pass

    def _cpu_fallback(self, exc: BaseException) -> None:
        self.fallback_reason = (f"GPU libraries could not be loaded ({exc}); Whisper ran on the CPU instead "
                                "(much slower). Run the launcher's Update / setup_windows.bat to install them.")
        self.opt.device, self.opt.compute_type = "cpu", "int8"
        self._model = self._load("cpu", "int8")

    def _run(self, fn):
        """Run fn(model); on a missing CUDA DLL (which can surface on first use) retry once on the CPU."""
        try:
            return fn(self.model())
        except (RuntimeError, OSError) as exc:
            if self.opt.device != "cuda" or not is_gpu_library_error(exc):
                raise
            self._cpu_fallback(exc)
            return fn(self._model)

    def vad_kwargs(self) -> dict:
        use = self.opt.vad and self.opt.vad_threshold > 0
        if self.opt.backend == "mlx":  # stable-ts' own Silero VAD (same threshold meaning)
            return {"vad": bool(use), "vad_threshold": self.opt.vad_threshold} if use else {"vad": False}
        out: dict = {"vad_filter": use}
        if use:
            out["vad_parameters"] = {"threshold": self.opt.vad_threshold, "speech_pad_ms": 500}
        return out

    def params(self, mode: str) -> dict:
        return {"engine": f"stable-ts/{self.opt.backend}", "model": self.opt.model, "device": self.opt.device,
                "compute_type": self.opt.compute_type, "vad": self.opt.vad, "vad_threshold": self.opt.vad_threshold,
                "mode": mode,
                "condition_on_previous_text": False, "word_timestamps": True}

    def detect_language(self, audio_path: str) -> str:
        if self.opt.backend == "mlx":  # MLX has no separate detector: transcribe the first 30 s and read it
            from mlx_whisper.audio import SAMPLE_RATE, load_audio

            clip = load_audio(audio_path)[: 30 * SAMPLE_RATE]
            res = self._run(lambda m: m.transcribe(clip, word_timestamps=False, regroup=False))
            return getattr(res, "language", None) or "en"
        from faster_whisper import decode_audio

        audio = decode_audio(audio_path, sampling_rate=16000)
        lang, _prob, _all = self._run(lambda m: m.detect_language(audio, **self.vad_kwargs()))
        return lang

    def transcribe(self, audio_path: str) -> Transcript:
        result = self._run(lambda m: m.transcribe(
            audio_path,
            language=self.opt.language or None,
            word_timestamps=True,
            **self.vad_kwargs(),                  # faster-whisper's built-in Silero VAD (no extra download)
            condition_on_previous_text=False,
            regroup=True,
        ))
        return Transcript(words_from_result(result), getattr(result, "language", None) or self.opt.language or "",
                          "transcribe", self.params("transcribe"))

    def align(self, audio_path: str, lyrics: str) -> Transcript:
        language = self.opt.language or self.detect_language(audio_path)
        result = self._run(lambda m: m.align(audio_path, lyrics, language=language, original_split=True))
        if result is None:
            raise RuntimeError("Forced alignment failed (stable-ts returned nothing). Try transcribing instead.")
        return Transcript(words_from_result(result), language, "align", self.params("align"))


class FakeEngine:
    """Deterministic engine for tests and dry runs: evenly spaced words."""

    def __init__(self, text: str = "hello world this is a test", language: str = "en", word_s: float = 0.4,
                 gap_s: float = 0.1, start: float = 1.0, confidence: float = 0.9):
        self.text, self.language, self.word_s, self.gap_s, self.start, self.conf = \
            text, language, word_s, gap_s, start, confidence

    def _words(self, lines: list[str]) -> list[TranscriptWord]:
        out, t = [], self.start
        for li, line in enumerate(lines):
            for tok in line.split():
                out.append(TranscriptWord(tok, round(t, 3), round(t + self.word_s, 3), self.conf, li))
                t += self.word_s + self.gap_s
            t += 1.0  # pause between lines
        return out

    def transcribe(self, audio_path: str) -> Transcript:
        return Transcript(self._words(self.text.splitlines() or [self.text]), self.language, "transcribe",
                          {"engine": "fake"})

    def align(self, audio_path: str, lyrics: str) -> Transcript:
        lines = [ln for ln in lyrics.splitlines() if ln.strip()]
        return Transcript(self._words(lines), self.language, "align", {"engine": "fake"})
