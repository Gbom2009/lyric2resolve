"""Phase 5: music analysis (synthetic audio), gaps, sanity flags."""

from __future__ import annotations

import numpy as np
import pytest

from lyric2resolve import project as proj
from lyric2resolve.analysis import analyze_project, gaps, sanity

pytest.importorskip("librosa")
from lyric2resolve.analysis import music  # noqa: E402

SR = 22050


def note(freq, t):
    return sum(np.sin(2 * np.pi * freq * h * t) / h for h in (1, 2, 3))


def synth_song(bpm=120.0, parts=((16, False), (16, True), (16, False)), sr=SR):
    """Kick on every beat (louder on beat 1), C-major pad; 'loud' parts add hats + bright chords."""
    out = []
    beat = 60.0 / bpm
    for seconds, loud in parts:
        t = np.arange(int(seconds * sr)) / sr
        phase = np.mod(t, beat)
        beat_idx = np.floor(t / beat).astype(int)
        accent = np.where(beat_idx % 4 == 0, 1.0, 0.45)
        kick = accent * np.sin(2 * np.pi * 50 * phase) * np.exp(-phase * 30)
        pad = 0.08 * (note(261.63, t) + note(329.63, t) + note(392.0, t))
        x = 0.8 * kick + pad
        if loud:
            hats = 0.15 * np.random.default_rng(0).standard_normal(len(t)) * (np.mod(t, beat / 2) < 0.02)
            lead = 0.15 * note(523.25, t) * (np.mod(t, beat) < beat * 0.7)
            x = 1.6 * x + hats + lead
        out.append(x)
    y = np.concatenate(out).astype(np.float32)
    return y / np.abs(y).max() * 0.9


@pytest.fixture(scope="module")
def analysis():
    return music.analyze(synth_song(), SR)


def test_bpm_and_beats(analysis):
    assert abs(analysis.bpm - 120) < 3 or abs(analysis.bpm - 60) < 2 or abs(analysis.bpm - 240) < 5
    d = np.diff(analysis.beats)
    assert abs(np.median(d) - 60 / analysis.bpm) < 0.02
    assert analysis.duration == pytest.approx(48, abs=0.1)


def test_downbeats_every_four_beats(analysis):
    db = np.array(analysis.downbeats)
    assert len(db) >= 10
    # downbeats should land on the accented kicks: times at multiples of 2.0 s (bar at 120 bpm)
    if abs(analysis.bpm - 120) < 3:
        assert np.median(np.abs(((db + 1.0) % 2.0) - 1.0)) < 0.08


def test_key_c_major(analysis):
    assert analysis.key in ("C major", "A minor")


def test_energy_curve(analysis):
    e = np.array(analysis.energy)
    assert len(e) == pytest.approx(48 * music.ENERGY_RATE, abs=2)
    assert e[200:300].mean() > 1.3 * e[30:130].mean()  # loud middle part
    assert e.max() <= 1.0 and e.min() >= 0.0


def test_sections_found_and_labelled(analysis):
    secs = analysis.sections
    starts = [s["start"] for s in secs]
    assert any(abs(s - 16) < 2.5 for s in starts) and any(abs(s - 32) < 2.5 for s in starts), starts
    loud = [s for s in secs if 18 < (s["start"] + s["end"]) / 2 < 30]
    assert loud and loud[0]["label"] == "chorus"


def test_key_silence():
    assert music.estimate_key(np.zeros(SR, dtype=np.float32)) == ("unknown", 0.0)


# ------------------------------------------------------------------ gaps
def W(i, text, s, e, c=0.9):
    return proj.Word(f"w{i:05d}", text, s, e, c)


def words_with_break():
    return [W(1, "one", 5.0, 5.5), W(2, "two", 5.6, 6.0), W(3, "three", 20.0, 20.5), W(4, "four", 20.6, 21.0)]


def test_detect_gaps_intro_break_outro():
    g = gaps.detect_gaps(words_with_break(), duration=40.0, min_gap_s=4.0)
    assert g == [(0.0, 5.0), (6.0, 20.0), (21.0, 40.0)]
    assert gaps.detect_gaps(words_with_break(), 22.0, 4.0) == [(0.0, 5.0), (6.0, 20.0)]
    assert gaps.detect_gaps([], 10.0, 4.0) == [(0.0, 10.0)]


def test_detect_gaps_ignores_sung_stretches():
    activity = [(4.9, 21.1)]  # someone sings throughout the break (ad-libs Whisper missed)
    g = gaps.detect_gaps(words_with_break(), 40.0, 4.0, activity)
    assert (6.0, 20.0) not in g and (21.0, 40.0) in g


def test_vocal_activity():
    sr = 16000
    t = np.arange(10 * sr) / sr
    y = np.where((t > 2) & (t < 4) | (t > 7) & (t < 8), np.sin(2 * np.pi * 300 * t), 0.0) * 0.5
    act = gaps.vocal_activity(y, sr, hangover_s=0.0)
    assert len(act) == 2
    assert act[0][0] == pytest.approx(2.0, abs=0.06) and act[0][1] == pytest.approx(4.0, abs=0.06)
    assert gaps.vocal_activity(np.zeros(sr), sr) == []


def test_apply_auto_gaps_keeps_manual():
    p = proj.Project(words=words_with_break())
    p.gaps = [proj.Gap("g0009", 7.0, 12.0, "manual"), proj.Gap("g0010", 30.0, 35.0, "auto")]
    gaps.apply_auto_gaps(p, [(0.0, 5.0), (6.0, 20.0)])
    assert [(g.start, g.end, g.source) for g in p.gaps] == [(0.0, 5.0, "auto"), (7.0, 12.0, "manual")]


def test_analyze_project_without_audio_uses_words():
    p = proj.Project(words=words_with_break())
    p.audio = {"duration_s": 30.0}
    flags = analyze_project(p)
    assert [(g.start, g.end) for g in p.gaps] == [(0.0, 5.0), (6.0, 20.0), (21.0, 30.0)]
    assert flags == []


# ------------------------------------------------------------------ sanity
def kinds(flags):
    return {(f.word_id, f.kind) for f in flags}


def test_sanity_flags_each_kind():
    words = [
        W(1, "fine", 1.0, 1.4),
        W(2, "zero", 1.5, 1.5),
        W(3, "blink", 1.6, 1.62),
        W(4, "overlapping", 1.55, 2.0),
        W(5, "mumble", 2.1, 2.4, c=0.2),
        W(6, "loooong", 3.0, 7.0),
        W(7, "far", 30.0, 30.4),
    ]
    p = proj.Project(words=words)
    flags = sanity.check(p, activity=[(0.9, 8.0)])
    k = kinds(flags)
    assert ("w00001", "zero_length") not in k
    assert ("w00002", "zero_length") in k and ("w00003", "very_short") in k
    assert ("w00004", "overlap") in k and ("w00005", "low_confidence") in k
    assert ("w00006", "very_long") in k and ("w00007", "outside_vocals") in k
    assert not any(f.word_id == "w00001" for f in flags)


def test_sanity_repeats_and_hallucinations():
    texts = ["la"] * 5 + ["oh", "yeah", "oh", "yeah", "oh", "yeah"] + ["Thank", "you", "for", "watching!"]
    p = proj.Project(words=[W(i + 1, t, i * 0.5, i * 0.5 + 0.3) for i, t in enumerate(texts)])
    flags = sanity.check(p)
    rep = [f for f in flags if f.kind == "repeat"]
    assert {f.word_id for f in rep} >= {"w00002", "w00005", "w00008", "w00011"}
    assert any(f.kind == "hallucination" and f.word_id == "w00012" for f in flags)
    # two repeats of a word are normal lyrics, not a loop
    p2 = proj.Project(words=[W(1, "go", 0, 0.3), W(2, "go", 0.4, 0.7), W(3, "now", 0.8, 1.0)])
    assert not [f for f in sanity.check(p2) if f.kind == "repeat"]


def test_flags_sorted_by_word_order():
    p = proj.Project(words=[W(1, "a", 0, 0, 0.1), W(2, "b", 1, 1, 0.1)])
    ids = [f.word_id for f in sanity.check(p)]
    assert ids == sorted(ids)


def test_missed_lyrics_flag_singing_without_words():
    """Fixes from testing: Whisper missed the whole first sentence -> point it out, with its time range."""
    from lyric2resolve import project as proj
    from lyric2resolve.analysis import sanity

    words = proj.make_words([{"text": t, "start": 10 + i * 0.5, "end": 10.4 + i * 0.5} for i, t in enumerate("a b c".split())])
    p = proj.Project(words=words, blocks=proj.blocks_by_line(words))
    activity = [(2.0, 3.0), (3.3, 5.5), (10.0, 11.5), (20.0, 20.8)]  # first line sung at 2-5.5 s, no words there
    flags = [f for f in sanity.check(p, activity) if f.kind == "missed_lyrics"]
    assert len(flags) == 1 and flags[0].start == 2.0 and flags[0].end == 5.5 and "0:02.00" in flags[0].message
    assert flags[0].word_id == words[0].id  # jumps to the next word
    assert sanity.check(p, activity)[0].kind == "missed_lyrics"  # listed in time order (it comes first)
    p.gaps = [proj.Gap("g1", 1.0, 6.0, "manual")]  # you marked it instrumental yourself -> no flag
    assert not [f for f in sanity.check(p, activity) if f.kind == "missed_lyrics"]
    assert sanity.missed_lyrics(p, None) == []
