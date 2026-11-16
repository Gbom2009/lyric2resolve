"""Ready-to-paste Claude Code prompts for (a) a Blender (bpy) project and (b) a three.js/WebGL scene.

Each prompt carries everything a fresh Claude Code session needs: BPM, section timings, mood, palette, duration,
fps/resolution/aspect, the available CC0 textures, and the render/delivery requirements.
"""

from __future__ import annotations

from .brief import Brief


def _sections_table(b: Brief) -> str:
    rows = ["| section | start (s) | end (s) | energy | concept ideas |", "|---|---|---|---|---|"]
    for s in b.sections:
        ideas = "; ".join(c["name"] for c in s.concepts)
        rows.append(f"| {s.label} | {s.start:.2f} | {s.end:.2f} | {s.level} ({s.energy}) | {ideas} |")
    return "\n".join(rows)


def _textures(textures: list[dict], limit: int = 25) -> str:
    if not textures:
        return "- (none downloaded yet - use procedural shaders, or run `lyric2resolve assets sync --textures`)"
    lines = []
    for t in textures[:limit]:
        maps = ", ".join(sorted((t.get("maps") or {}).keys()))
        lines.append(f"- {t['name']} ({t.get('category', '')}, {t.get('kind', 'texture')}, {t.get('license', '')}): "
                     f"{t.get('path', '')} [{maps}]")
    return "\n".join(lines)


def blender_prompt(b: Brief, fps: float, aspects: list[str], textures: list[dict], curves_path: str = "curves.json",
                   textures_root: str = "") -> str:
    sizes = " and ".join("1920x1080" if a == "16:9" else "1080x1920" for a in aspects)
    return f"""You are building an audio-reactive music visual in Blender with Python (bpy), run headless.

## Song
- Title: {b.title} — duration {b.duration} s, BPM {b.bpm or 'unknown'} ({b.tempo_feel}), key {b.key}
- Mood: {b.mood}; lyric themes: {', '.join(b.themes) or 'none detected'}; keywords: {', '.join(b.keywords) or '-'}
- Palette (hex): {', '.join(b.palette)}

## Sections (seconds from the song start)
{_sections_table(b)}

## Audio data
`{curves_path}` holds per-frame curves at exactly {fps} fps (frame index 0 = song start), values 0..1:
bass (20-150 Hz), mids (150-2000 Hz), highs (2000-12000 Hz), rms, onset, beat (decaying pulse on each beat).
Load it with json; keyframe them as custom properties on one controller empty and drive the scene with
simple-expression drivers (no Python auto-run needed). Do not re-analyse audio in Blender.

## Look
- Default mapping: bass = glowing orange + scale pulse, mids = glowing blue, highs = glowing green + sparkles,
  rms -> light intensity, beat -> subtle camera shake. Chorus/drop brighter than verses (use the section table).
- Per section, pick one concept from the table and make the transitions on section boundaries.

## Available CC0 textures (root: {textures_root or '<data folder>/assets/textures'})
{_textures(textures)}
Layer audio-reactive emission on top of these PBR textures (mask from height/noise/crack pattern). Pack textures
into the .blend (bpy.ops.file.pack_all) so it is portable.

## Render requirements
- Blender 4.2 LTS - 5.x compatible API (slotted actions in 4.4+: use keyframe_insert / channelbag helpers).
- {fps} fps (NTSC rates as fps/fps_base, e.g. 24/1.001), frames 1..{round(b.duration * fps)}, resolution {sizes};
  make one camera setup per aspect ratio ({', '.join(aspects)}), each saved as its own .blend.
- Eevee by default (fast), optional Cycles; bloom via the compositor Glare node; colour management AgX.
- Output PNG sequence to frames/<aspect>/frame_####.png, overwrite off (resumable), placeholders on.
- Must render headless with: blender -b scene_16x9.blend -a
- Write RENDER_INSTRUCTIONS.md for a beginner (prereqs, settings and why, CLI + GUI steps, time estimate,
  preview first, resume, import into DaVinci Resolve on V1 under the lyric titles, troubleshooting).
- Final MP4 for DJ decks: H.264 High yuv420p, constant {fps} fps, keyframe every <=25 frames, AAC 320 kbps with
  the full song muxed in (ffmpeg), max 1920x1080 for Rekordbox.

Start with a 25-second low-res preview (540p, 15 fps) and show me a frame before the full render.
"""


def threejs_prompt(b: Brief, fps: float, aspects: list[str], textures: list[dict], curves_path: str = "curves.json") -> str:
    return f"""Build an audio-reactive three.js (WebGL) scene for a music video, rendered frame-accurately (not real time).

## Song
- {b.title}: {b.duration} s, BPM {b.bpm or 'unknown'} ({b.tempo_feel}), key {b.key}, mood {b.mood}
- Palette: {', '.join(b.palette)}; lyric themes: {', '.join(b.themes) or '-'}

## Sections
{_sections_table(b)}

## Audio data
Use `{curves_path}` (per-frame curves at {fps} fps: bass, mids, highs, rms, onset, beat; 0..1). Drive everything
from the frame index, never from wall-clock time or live WebAudio analysis, so every render is identical.

## Textures (CC0, optional)
{_textures(textures, 12)}

## Requirements
- Plain ES modules + three.js from a CDN pinned to an exact version; one index.html, no build step.
- Canvas sizes: {', '.join('1920x1080' if a == '16:9' else '1080x1920' for a in aspects)} (switch with ?aspect=16:9|9:16).
- A "Render" button steps frame by frame at {fps} fps and saves PNGs (e.g. CCapture.js or toBlob + download zip).
- Bloom via UnrealBloomPass; bass = orange glow + scale pulse, mids = blue, highs = green sparkles.
- Include RENDER_INSTRUCTIONS.md: how to serve locally, capture frames, and mux with the song
  (ffmpeg H.264 High, yuv420p, CFR {fps} fps, GOP <=25, AAC 320 kbps) for DaVinci Resolve and DJ decks.
"""


def brief_markdown(b: Brief) -> str:
    lines = [f"# Visual ideas — {b.title}", "",
             f"- Duration {b.duration} s · BPM {b.bpm or '?'} ({b.tempo_feel}) · key {b.key}",
             f"- Mood **{b.mood}** · themes: {', '.join(b.themes) or 'none detected'}",
             f"- Palette: {' '.join(b.palette)}", ""]
    for s in b.sections:
        lines.append(f"## {s.label.title()} ({s.start:.1f}-{s.end:.1f} s, energy {s.level})")
        for c in s.concepts:
            lines.append(f"- **{c['name']}** (`--template {c['template']}`): {c['idea']}")
        lines.append(f"- Text animation: {' / '.join(s.text_animation)}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """lyric2resolve ideas project.json [--out DIR]  -> brief + Blender/three.js prompts as Markdown files."""
    import argparse
    from pathlib import Path

    from lyric2resolve import project as proj
    from lyric2resolve.assets import textures

    from .brief import build_brief

    ap = argparse.ArgumentParser(prog="lyric2resolve ideas")
    ap.add_argument("project", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    p = proj.load(args.project)
    b = build_brief(p)
    out = args.out or args.project.parent / "visuals" / "ideas"
    out.mkdir(parents=True, exist_ok=True)
    tex = textures.list_textures()
    files = {"VISUAL_IDEAS.md": brief_markdown(b),
             "PROMPT_blender.md": blender_prompt(b, p.settings.fps, list(p.settings.layouts), tex),
             "PROMPT_threejs.md": threejs_prompt(b, p.settings.fps, list(p.settings.layouts), tex)}
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
        print("written:", out / name)
    return 0
