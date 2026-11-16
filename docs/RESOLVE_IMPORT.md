# Importing the lyrics timeline into DaVinci Resolve

## A. FCPXML (works in Resolve free and Studio)
1. In the editor click **Export…** (or run `lyric2resolve export <project.json>`). You get one file per layout:
   `<song>_16x9.fcpxml` (1920×1080) and `<song>_9x16.fcpxml` (1080×1920), in the project's `export` folder.
2. In Resolve: open/create a project, then **File → Import → Timeline…** and pick the `.fcpxml`.
   - Leave "Automatically import source clips into media pool" **on** (the song is linked by its full path).
   - If Resolve asks about the frame rate, accept the timeline's rate. Set the *project* frame rate to the same fps
     **before** importing when possible (Project Settings → Master Settings) — Resolve cannot change a project's fps
     after media is added.
3. You get a timeline starting at **01:00:00:00** with the full song on an audio track, one title per lyric block on a
   video track, and markers for sections and bars. There is nothing on the timeline inside instrumental gaps.
4. For the vertical version import the `_9x16` file as well; it creates its own 1080×1920 timeline.

### If the titles arrive as generic "Text" titles instead of Fusion Text+
That is normal for FCPXML: Resolve converts Apple "Basic Title" clips into its own simple **Text** title. Timing and
text are correct; font/size/colour come over partly (Resolve ignores some FCPXML style attributes and the position).
Options:
- **Use the Resolve script export (recommended for styling)** — `resolve_build_timeline.py` (next phase) builds the
  timeline inside Resolve with real **Text+** clips and your style preset/animations.
- Keep the Text titles and restyle them all at once: select all titles on the track, then change font/size/colour in
  the Inspector (multi-selection edits apply to every selected title).
- Missing font? Library page → Fonts → **Install fonts for Resolve** (or `lyric2resolve assets install-fonts`), then restart Resolve. Mac: fonts go to `~/Library/Fonts`.

### If the song shows as "media offline"
The FCPXML points at the original song file. If you moved it, right-click the clip in the Media Pool → *Relink
Selected Clips…* and point to the new folder.

## Why there is no `.drp` file
A `.drp` is Resolve's own project export: an undocumented, proprietary archive of Resolve's internal database. There is
no public format specification, so generating one would be guesswork that could break with any Resolve update. FCPXML
(an open interchange format Resolve officially imports) and Resolve's official scripting API are the supported routes.
