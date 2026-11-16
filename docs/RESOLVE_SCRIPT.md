# Building the timeline inside Resolve with real Text+ (script route)

Works in DaVinci Resolve **free** and Studio. Uses only Resolve's official scripting API
(`Help > Documentation > Developer` → `Scripting/README.txt`).

## One-time setup: the Text+ template
Resolve's API cannot create a Text+ title with an exact length, so the script copies a small
**Fusion Composition** from the Media Pool for every lyric line:
1. In the Edit page, right-click an empty spot in the **Media Pool** → **New Fusion Composition**.
2. Rename the new clip to **`l2r_textplus`** (exact name). Give it a long duration (e.g. 1 minute: right-click →
   Clip Attributes, or set it when creating it) so it is longer than your longest lyric line.
3. (Optional) Open it in the Fusion page and add a **Text+** connected to MediaOut. If you skip this, the script adds
   the Text+ tool itself.
Tip: do this in an empty project you use as your lyric-video starting point, so the template is always there.

## Every song
1. In the editor: **Export…** → tick **Resolve script** (also writes the FCPXML). The script is copied to your Resolve
   scripts folder automatically:
   `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\lyric2resolve_build_timeline.py`
2. In Resolve open the project (frame rate must match the export, e.g. 25 fps — set it in Project Settings **before**
   adding media).
3. **Workspace → Scripts → Utility → lyric2resolve_build_timeline**.
4. You get one timeline per layout (`… 16x9 (l2r)` and `… 9x16 (l2r)`): song on A1, one Text+ per lyric block on V1 at
   the exact frames, markers for sections/bars. Nothing is placed in instrumental gaps.

What the styling level does:
- **BASIC** – Text+ with font, size, colour and position only.
- **STYLED** – plus outline, drop shadow and glow (SoftGlow node) from your style preset.
- **FULL** – plus simple animations: fade in/out, pop, slide up, or word-by-word reveal (Write On).

If no `l2r_textplus` item is found, the script imports the FCPXML instead (exact timing, simple titles) and says so in
**Workspace → Console**.

## If something goes wrong
Open **Workspace → Console** (Py3 tab) to read the script's messages. Common cases:
- *"project runs at X fps"* → make a new project at the export's fps.
- *"No lyric2resolve export found"* → export with "Resolve script" ticked first.
- Text too big/small or in the wrong place → these Text+ parameter mappings are verified on your PC (see
  VERIFY_LOCAL.md); report the Resolve version and what you see.
