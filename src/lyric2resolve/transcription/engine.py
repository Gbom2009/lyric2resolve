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
    model_dir: str | None = None  # download/cache folder (data/models/whisper)


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


class StableTsEngine:
    """stable-ts + faster-whisper. Loads the model lazily on first use."""

    def __init__(self, options: EngineOptions | None = None):
        self.opt = options or EngineOptions()
        self._model = None

    def model(self):
        if self._model is None:
            import stable_whisper  # heavy, PC only

            kwargs = {"device": self.opt.device, "compute_type": self.opt.compute_type}
            if self.opt.model_dir:
                kwargs["download_root"] = self.opt.model_dir
            self._model = stable_whisper.load_faster_whisper(self.opt.model, **kwargs)
        return self._model

    def params(self, mode: str) -> dict:
        return {"engine": "stable-ts/faster-whisper", "model": self.opt.model, "device": self.opt.device,
                "compute_type": self.opt.compute_type, "vad": self.opt.vad, "mode": mode,
                "condition_on_previous_text": False, "word_timestamps": True}

    def detect_language(self, audio_path: str) -> str:
        from faster_whisper import decode_audio

        lang, _prob, _all = self.model().detect_language(decode_audio(audio_path, sampling_rate=16000),
                                                         vad_filter=self.opt.vad)
        return lang

    def transcribe(self, audio_path: str) -> Transcript:
        result = self.model().transcribe(
            audio_path,
            language=self.opt.language or None,
            word_timestamps=True,
            vad_filter=self.opt.vad,              # faster-whisper's built-in Silero VAD (no extra download)
            condition_on_previous_text=False,
            regroup=True,
        )
        return Transcript(words_from_result(result), getattr(result, "language", None) or self.opt.language or "",
                          "transcribe", self.params("transcribe"))

    def align(self, audio_path: str, lyrics: str) -> Transcript:
        language = self.opt.language or self.detect_language(audio_path)
        result = self.model().align(audio_path, lyrics, language=language, original_split=True)
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
