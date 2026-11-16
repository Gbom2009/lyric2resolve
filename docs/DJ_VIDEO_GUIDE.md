# DJ video guide — Rekordbox & Serato

Your lyric video is played straight from the DJ software (Rekordbox video / Serato Video) out over HDMI. Both
play **one MP4 file that contains the video AND the full-quality song**. A video without an audio track cannot be
played on its own in Rekordbox.

What the decks accept (checked 2026-11-16 —
[rekordbox FAQ video-5](https://rekordbox.com/en/support/faq/video-5),
[rekordbox FAQ video-7](https://rekordbox.com/en/support/faq/video-7),
[Serato Video formats](https://support.serato.com/hc/en-us/articles/202305724-Serato-Video-supported-formats-and-codecs)):
- **Rekordbox**: MP4/MOV/M4V, H.264 (or MPEG-4/MPEG-2), audio AAC/MP3/PCM, video **up to 1920×1080**.
- **Serato**: recommends **MP4 + H.264 + AAC**, with a **keyframe every 15–25 frames**; portrait 1080×1920 is listed for
  its visualizer.
So: **H.264 + AAC in MP4, 1080p, constant frame rate, keyframe ≤ 25 frames** works on both.

## A. Final render from DaVinci Resolve (Deliver page)
Use the timeline that has the song + lyrics (+ the Blender background on V1).

| Setting | 16:9 (Rekordbox + Serato) | 9:16 (Serato portrait / socials) |
|---|---|---|
| Render | Single clip | Single clip |
| Format | **MP4** | **MP4** |
| Codec | **H.264** (pick the *NVIDIA* encoder if listed, otherwise *Native*) | H.264 |
| Resolution | **1920 × 1080** | 1080 × 1920 (Rekordbox: use the 16:9 file, or a 608 × 1080 copy) |
| Frame rate | **same as the timeline** (e.g. 25) | same as the timeline |
| Quality | Restrict to **16 000–20 000 Kb/s** | 16 000–20 000 Kb/s |
| Encoding profile | **High** | High |
| Key frames | **Every 25 frames** (or 1 s) | Every 25 frames |
| Frame reordering | off | off |
| Audio codec | **AAC** | AAC |
| Audio data rate | **320 Kb/s** | 320 Kb/s |
| Sample rate | **48 000 Hz** (44 100 also fine) | 48 000 Hz |
| Channels | Stereo (2) | Stereo |
| Render timeline | **Entire timeline** (starts exactly at 01:00:00:00 = song start) | Entire timeline |

Name the file like the track (e.g. `Artist - Title (lyrics).mp4`) so it is easy to find in the library.

## B. Videos rendered by lyric2resolve itself
Blender backgrounds and previews rendered with `lyric2resolve render` already get the song muxed in with these
settings (H.264 High, yuv420p, constant frame rate, keyframe every ≤ 25 frames, AAC 320 kbps 48 kHz, faststart).
Files larger than 1920×1080 also get a `_dj.mp4` copy that fits Rekordbox.

## C. Check the sync on the decks
1. Import the MP4 into Rekordbox/Serato like any track; let it analyse (beatgrid).
2. Play from a hard transient (first kick / a drop) and watch: the lyric must appear exactly on the sung word, the
   Blender pulses exactly on the kicks.
3. Jump to the **last chorus** and check again — drift at the end means an fps mismatch (render fps ≠ timeline fps).
4. Compare with the original audio file: load both on two decks, sync, and listen for flanging (= audio offset).
5. If everything is late by a fixed amount on your setup, use the global **sync offset** in the editor
   (Text & timing options) and re-export, rather than shifting things in Resolve.
6. Test the actual HDMI output once before a gig (some projectors add latency; that affects the audience view only).
