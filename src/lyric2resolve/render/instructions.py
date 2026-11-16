"""RENDER_INSTRUCTIONS.md for every generated visual (beginner level)."""

from __future__ import annotations

from .presets import PRESETS, RenderPreset


def blender_markdown(name: str, template: str, fps: float, frames: int, duration_s: float, preset: RenderPreset,
                     aspects: list[str], blend_names: dict[str, str], frames_dirs: dict[str, str],
                     sec_per_frame_hint: float | None = None) -> str:
    sizes = ", ".join(f"{a}: {preset.size(a)[0]}x{preset.size(a)[1]}" for a in aspects)
    a0 = aspects[0]
    blend = blend_names[a0]
    est = ""
    if sec_per_frame_hint:
        total = sec_per_frame_hint * frames
        est = f"\nMeasured on your PC: about {sec_per_frame_hint:.1f} s per frame -> {total / 60:.0f} minutes for all frames.\n"
    rows = "\n".join(f"| {p.name.upper()} | {p.size('16:9')[0]}x{p.height} | {p.engine.title()} | {p.samples} | "
                     f"{p.description} |" for p in PRESETS.values())
    return f"""# Render instructions — {name} ({template.replace('_', ' ')})

This folder contains an audio-reactive Blender scene made by lyric2resolve for your song.
Everything here can be rendered by the app (`lyric2resolve render …`), but these steps let you do it by hand too.

## 1. What you need
- **Blender 4.2 LTS or newer** (tested with 5.3) — https://www.blender.org/download/ (free).
- **NVIDIA driver** up to date (GeForce/Studio driver). Eevee uses the GPU automatically; Cycles needs
  *Edit → Preferences → System → Cycles Render Devices → OptiX* (RTX cards) or *CUDA* (older cards).
- **ffmpeg** (to turn the frames into an MP4 with the song): `winget install Gyan.FFmpeg`.
- **Mac (Apple Silicon)**: Blender from blender.org dragged into Applications; Eevee and Cycles render on the GPU
  through **Metal** (Cycles: *Preferences → System → Cycles Render Devices → Metal*). ffmpeg: `brew install ffmpeg`
  (the app encodes with Apple's hardware encoder, VideoToolbox). On an 8 GB / fanless MacBook Air use Preview or
  Draft while working and Standard only for the final video, with other apps closed.

## 2. Settings and why
| Setting | Value here | Why |
|---|---|---|
| Engine | {preset.engine.title()} | Eevee is real-time and fast (minutes); Cycles is path-traced: prettier light, much slower (hours). |
| Samples | {preset.samples} | More samples = less noise/flicker in glow; preview can be low. |
| Resolution | {sizes} | Match your Resolve timeline (1920x1080 or 1080x1920). DJ decks (Rekordbox) play max 1920x1080. |
| Frame rate | {fps} fps | Must equal the Resolve timeline fps, otherwise the beat sync drifts. |
| Frame range | 1 – {frames} ({duration_s:.1f} s) | Frame 1 = the first moment of the song. |
| Colour management | {preset.view_transform} | Handles bright neon glow without ugly clipping (Filmic on older Blender). |
| Output | PNG sequence in `frames/…` | A crash never ruins the whole render, and you can resume. |
| Bloom/glow | {'on' if preset.bloom else 'off'} (compositor Glare node) | The glowing look. |

Presets the app offers:

| Preset | Size (16:9) | Engine | Samples | Use |
|---|---|---|---|---|
{rows}

## 3. Quick preview first
Render a short low-res preview before the long render:
```
lyric2resolve render <project.json> --template {template} --render-preset preview
```
(540p, 15 fps, first 25 seconds). Check the look and the beat sync, then do the real render.

## 4. Render from the command line (recommended)
```
blender -b "{blend}" -a
```
Frames are written to `{frames_dirs[a0]}`. Blender skips frames that already exist, so you can **stop
(Ctrl+C) and resume** by running the same command again. To render only part: `-s 250 -e 500 -a`.
{est}
## 5. Render from the Blender window
1. Open `{blend}` in Blender.
2. Check *Output Properties*: resolution, frame range, fps, output folder (`frames/…`), file format PNG.
3. *Render → Render Animation* (Ctrl+F12). Close the window to stop; start again to resume (Overwrite is off).

## 6. Frames → MP4 with the song
The app does this for you. By hand (16:9, {fps} fps):
```
ffmpeg -framerate {fps} -start_number 1 -i frames/{a0.replace(':', 'x')}/frame_%04d.png -i "<song>" -map 0:v -map 1:a ^
  -vf format=yuv420p -c:v libx264 -preset slow -crf 18 -profile:v high -r {fps} -fps_mode cfr -g {min(25, round(fps))} ^
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart visual_{a0.replace(':', 'x')}.mp4
```

## 7. Import into DaVinci Resolve
1. Import the MP4 (or the PNG sequence) into the Media Pool.
2. Put it on **V1, under the lyric titles** (titles on V2 or above).
3. Timeline fps and resolution must match ({fps} fps, {sizes}). If you rendered 1080p for a 4K timeline,
   Resolve can upscale (*Super Scale* in Studio, or plain scaling).
4. Align the first frame with the start of the song (01:00:00:00); the section/bar markers help to check sync.
5. Shorter than the song (preview/section render)? Loop it or stretch it — or render the full length.

## 8. Render time
Eevee 1080p on a modern RTX card: roughly 0.2–1 s per frame. Cycles: 5–60 s per frame.
A 4-minute song at {fps} fps = {round(240 * fps)} frames. The app renders 3 test frames first and tells you the estimate.
Time savers: render selected sections only, render at 30 fps, render 1080p and upscale in Resolve.

## 9. Troubleshooting
- **Black frames** → the scene's light/emission is too low or the camera is inside an object: check in the viewport.
- **Very slow Cycles** → GPU not enabled (Preferences → System); or use Eevee.
- **"Out of GPU memory"** → lower resolution/samples, or switch Cycles device to CPU.
- **Flickering glow** → more samples, or slightly longer release in `curves`/mapping.
- **Visuals out of sync** → fps mismatch between render and Resolve timeline; re-render at the timeline fps.
- **Textures pink/missing** → textures are packed in the .blend; if you unpacked them, keep the folders next to it.
- **Alternative audio sync**: instead of our curves you can use *Graph Editor → Channel → Bake Sound to F-Curves*
  on any property (select a keyframed property, choose the song, set the frequency band).
"""


def threejs_markdown(name: str, fps: float, aspects: list[str]) -> str:
    return f"""# Render instructions — {name} (three.js / WebGL)

1. Requirements: a recent Chrome/Edge, ffmpeg (`winget install Gyan.FFmpeg`), Node.js only if the scene says so.
2. Open the scene's `index.html` through a local server (e.g. `python -m http.server`), not by double-clicking.
3. Record deterministically: the scene must render frame by frame at {fps} fps (fixed time step, not real time) and
   save PNGs (e.g. with CCapture.js or a "capture" button); real-time screen recording drops frames.
4. Combine frames + song with the ffmpeg command from the Blender instructions (same settings: H.264, CFR,
   AAC 320 kbps). Sizes: {", ".join(aspects)} → 1920x1080 / 1080x1920.
5. Import into Resolve on V1 under the titles; fps must match the timeline.
Troubleshooting: if audio-reactive values look late, check that the analysis uses the same fps and starts at frame 0.
"""
