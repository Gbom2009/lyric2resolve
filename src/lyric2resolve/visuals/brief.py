"""Visual style brief from the song: lyric themes/mood, BPM, key, energy curve and sections.

Rule/template based (works offline, no AI). The Claude link (Phase 17) can generate richer briefs on top.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from lyric2resolve.project import Project

THEMES = {
    "romantic": ("love", "heart", "kiss", "baby", "together", "hold", "forever", "touch", "liefde", "hart"),
    "dark": ("night", "dark", "shadow", "black", "devil", "ghost", "fear", "nacht", "donker"),
    "fiery": ("fire", "burn", "heat", "flame", "hot", "blaze", "vuur"),
    "euphoric": ("dance", "party", "tonight", "high", "alive", "jump", "hands", "feel", "dansen"),
    "melancholic": ("rain", "tears", "cry", "alone", "lost", "goodbye", "cold", "regen", "alleen"),
    "dreamy": ("dream", "sky", "stars", "fly", "float", "cloud", "moon", "heaven", "droom"),
    "bold": ("money", "gold", "king", "queen", "boss", "crown", "power"),
    "fluid": ("ocean", "water", "wave", "sea", "river", "flow", "drown"),
    "urban": ("city", "neon", "lights", "drive", "street", "car", "club"),
}

PALETTES = {
    "romantic": ["#ff4d8d", "#ff9ec4", "#7a1f5c"], "dark": ["#7b2cff", "#1a0b2e", "#ff2a6d"],
    "fiery": ["#ff7a1a", "#ff2a00", "#ffd000"], "euphoric": ["#00e5ff", "#ff3df0", "#ffe14d"],
    "melancholic": ["#4d7cff", "#9bb7d4", "#1c2541"], "dreamy": ["#b18cff", "#6ee7ff", "#ffd6f5"],
    "bold": ["#ffd000", "#111111", "#ff3b30"], "fluid": ["#00c2ff", "#0047ab", "#7fffd4"],
    "urban": ["#ff2a6d", "#05d9e8", "#d1f7ff"], "neutral": ["#ff7a1a", "#2f7bff", "#33ff88"],
}

CONCEPTS = [
    {"name": "Neon floor grid", "template": "floor_grid", "moods": {"urban", "euphoric", "dark"}, "energy": (0.4, 1.0),
     "idea": "Synthwave grid flying towards a glowing sun; grid lines flash on the kick, horizon colour shifts per section."},
    {"name": "Spectrum bars", "template": "spectrum_bars", "moods": {"euphoric", "bold", "urban"}, "energy": (0.3, 1.0),
     "idea": "Classic equaliser bars: bass on the left glowing orange, highs on the right green; bars jump with the music."},
    {"name": "Pulsing blob", "template": "pulsing_blob", "moods": {"fluid", "dreamy", "romantic"}, "energy": (0.0, 0.8),
     "idea": "Soft liquid-like sphere that breathes with the bass and ripples with the mids, ring orbiting it."},
    {"name": "Hyperspace tunnel", "template": "tunnel", "moods": {"euphoric", "dark", "urban"}, "energy": (0.6, 1.0),
     "idea": "Fly through glowing rings; ring colours cycle bass/mids/highs, speed and spin rise in the drop."},
    {"name": "Particle field", "template": "particle_field", "moods": {"dreamy", "romantic", "melancholic"},
     "energy": (0.0, 0.7), "idea": "Floating sparkles around a glowing core; highs make the sparkles flash like stars."},
    {"name": "Lava cracks", "template": "pulsing_blob", "moods": {"fiery", "dark", "bold"}, "energy": (0.5, 1.0),
     "idea": "Dark rock with glowing cracks (cracked-rock/lava texture + procedural crack mask) erupting on the kick."},
    {"name": "Rain on glass", "template": "particle_field", "moods": {"melancholic", "fluid"}, "energy": (0.0, 0.5),
     "idea": "Blurred city lights behind falling droplets; droplets brighten on vocals, slow camera drift."},
    {"name": "Chrome liquid", "template": "pulsing_blob", "moods": {"fluid", "bold", "urban"}, "energy": (0.3, 0.9),
     "idea": "Reflective metal blob (brushed metal texture, dark HDRI) morphing on the mids, glints on the highs."},
    {"name": "Low-poly mountains", "template": "floor_grid", "moods": {"dreamy", "melancholic", "neutral"},
     "energy": (0.0, 0.6), "idea": "Flat-shaded low-poly terrain at dusk; sky colour follows the energy curve."},
]

TEXT_ANIMATIONS = {
    "low": ["Soft fade in per line, hold until the next line", "Slow slide up (6-8 px) with a soft glow"],
    "mid": ["Line fades in, current word brightens (karaoke style)", "Gentle pop on the first word of each line"],
    "high": ["Word-by-word pop on the beat", "Scale punch on every downbeat + quick fade out",
             "Big centred words, one per beat (WORD preset)"],
}


@dataclass
class SectionBrief:
    label: str
    start: float
    end: float
    energy: float
    level: str                 # low | mid | high
    concepts: list[dict] = field(default_factory=list)
    text_animation: list[str] = field(default_factory=list)


@dataclass
class Brief:
    title: str
    duration: float
    bpm: float | None
    key: str
    tempo_feel: str
    themes: list[str]
    mood: str
    palette: list[str]
    keywords: list[str]
    sections: list[SectionBrief]

    def to_dict(self) -> dict:
        return asdict(self)


def lyric_themes(text: str) -> tuple[list[str], list[str]]:
    words = re.findall(r"[a-zà-ÿ']+", text.lower())
    counts = Counter()
    hits = Counter()
    for w in words:
        for theme, keys in THEMES.items():
            if w in keys or (len(w) > 4 and any(w.startswith(k) for k in keys if len(k) > 3)):
                counts[theme] += 1
                hits[w] += 1
    themes = [t for t, _ in counts.most_common(3)]
    return themes, [w for w, _ in hits.most_common(8)]


def tempo_feel(bpm: float | None) -> str:
    if not bpm:
        return "unknown tempo"
    if bpm < 95:
        return "slow / laid-back"
    if bpm <= 125:
        return "mid-tempo groove"
    return "fast / club energy"


def _section_energy(p: Project, start: float, end: float) -> float:
    e = p.analysis.get("energy") or []
    rate = float(p.analysis.get("energy_rate") or 10.0)
    seg = e[int(start * rate):max(int(start * rate) + 1, int(end * rate))]
    return float(sum(seg) / len(seg)) if seg else 0.6


def build_brief(p: Project) -> Brief:
    text = " ".join(w.text for w in p.words) or (p.lyrics or "")
    themes, keywords = lyric_themes(text)
    key = str(p.analysis.get("key") or "unknown")
    bpm = p.analysis.get("bpm")
    mood = themes[0] if themes else ("dark" if "minor" in key else "euphoric" if bpm and bpm > 120 else "neutral")
    duration = float(p.audio.get("duration_s") or p.analysis.get("duration") or (p.words[-1].end if p.words else 0))
    secs = p.sections or []
    if not secs:
        from lyric2resolve.project import Section

        secs = [Section("all", "song", 0.0, duration)]
    moods = set(themes) | {mood}
    out_secs = []
    for s in secs:
        en = _section_energy(p, s.start, s.end)
        level = "high" if en >= 0.75 or s.label in ("drop", "chorus") and en >= 0.6 else "low" if en < 0.45 else "mid"
        scored = []
        for c in CONCEPTS:
            lo, hi = c["energy"]
            score = 2.0 * len(c["moods"] & moods) + (1.5 if lo <= en <= hi else 0.0)
            if s.label in ("drop", "chorus") and c["template"] in ("tunnel", "floor_grid", "spectrum_bars"):
                score += 1.0
            if s.label in ("intro", "outro", "bridge", "breakdown") and c["template"] in ("particle_field", "pulsing_blob"):
                score += 1.0
            scored.append((score, c["name"], c))
        top = [c for _, _, c in sorted(scored, key=lambda x: (-x[0], x[1]))[:3]]
        out_secs.append(SectionBrief(s.label, s.start, s.end, round(en, 2), level,
                                     [{"name": c["name"], "template": c["template"], "idea": c["idea"]} for c in top],
                                     TEXT_ANIMATIONS[level]))
    return Brief(p.name, round(duration, 2), round(bpm, 1) if bpm else None, key, tempo_feel(bpm), themes, mood,
                 PALETTES.get(mood, PALETTES["neutral"]), keywords, out_secs)
