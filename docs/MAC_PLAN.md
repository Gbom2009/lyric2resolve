# lyric2resolve for Mac (Apple Silicon M1–M4) — plan

Status: phases 1-2 merged (PRs #10, #11), `mac-release` created; phase 3 (MLX Whisper) merged (#12); phase 4 (rendering: VideoToolbox, Metal, 8 GB presets) PR #13; phase 5 (integration) branch `mac-integration`. The macOS CI job is cancelled by GitHub on this account (billing/minutes): the user chose to continue with the MacBook as the Mac test. Branch `mac-app`. The Windows app keeps working exactly as it is:
one code base, with Mac-specific parts behind the same small interfaces (like the GPU/Whisper/ffmpeg ones already are).

## Goal
A real Mac app: download → double-click **lyric2resolve.app** in Applications/Dock → same editor, Visuals, Karaoke,
Assistant, clips and Resolve export as on Windows, using the M chip's GPU/Neural Engine where it matters, and the same
**Update now** button (git-based, with rollback).

## What changes (and why)
| Area | Windows today | Mac (M chips) |
|---|---|---|
| Install | `install.bat` + Desktop shortcut | `install.command` (double-click in Finder) → builds `lyric2resolve.app` in /Applications (+ Dock); checks Xcode command-line tools (git), Python, Homebrew ffmpeg |
| App window/launcher | `launcher.pyw` via pythonw shortcut | the same launcher inside a small `.app` bundle (Info.plist, icon, no Terminal window) |
| PyTorch | CUDA wheels from download.pytorch.org | standard macOS arm64 wheels, **MPS** (Metal) GPU; the torch health check knows MPS |
| Whisper | faster-whisper (CTranslate2) on CUDA | CTranslate2 has **no Mac GPU** → add an **MLX Whisper** engine (Apple's own ML framework, fast on M chips, large-v3 incl. word timestamps); faster-whisper on CPU int8 stays as fallback; forced alignment (your lyrics) via stable-ts on CPU/MPS |
| Vocal separation | audio-separator (CUDA, onnxruntime-gpu) | `audio-separator[cpu]` + CoreML/MPS (BS-Roformer runs on MPS); slower than an RTX card, still fine |
| Video encode | NVENC → libx264 | **VideoToolbox** (`h264_videotoolbox`, hardware) → libx264 fallback; same Rekordbox/Serato checks |
| Blender | `C:\Program Files\Blender…` | `/Applications/Blender.app/Contents/MacOS/Blender`; Cycles **Metal** GPU (instead of OptiX/CUDA), Eevee on Metal |
| ffmpeg / Claude CLI | PATH / WinGet / npm folders | Homebrew `/opt/homebrew/bin` (a double-clicked app does not get your Terminal PATH), `~/.local/bin/claude` |
| Fonts for Resolve | per-user Windows font install | copy to `~/Library/Fonts` |
| Resolve script | `%APPDATA%\…\Scripts\Utility` | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility` (already in the code; verify) |
| Data folder | `%LOCALAPPDATA%\lyric2resolve` | `~/Library/Application Support/lyric2resolve` (already in the code) |
| Windows-only fixes | Store-Python redirection, `taskkill`, `CREATE_NO_WINDOW`, `.cmd` | not used on Mac; process-group kill for Stop instead of `taskkill` |
| CI | Linux + Windows + Blender | **+ macOS 14 (Apple Silicon) runner**: unit + browser tests, install smoke test, app bundle build |

## Phases (each one PR, merged when CI is green — like the Windows updates)
1. **Mac foundation** — platform layer (`paths`, `setup_tools`: Homebrew/`/Applications` lookups, GPU = Apple Silicon/MPS
   detection, `sysctl` chip/RAM info), Mac requirements group, `setup_mac.command`, macOS CI job (tests on M-chip runner).
2. **App bundle + installer** — `install.command` → `/Applications/lyric2resolve.app` (Info.plist, icon, launcher inside,
   no Terminal), Dock/Launchpad, the updater works from the app (self-update + rollback), INSTALL_MAC.md.
   Unsigned at first: first start = right-click → Open (Gatekeeper); notarisation later only if you want it
   (needs a paid Apple Developer account).
3. **Whisper on the M chip** — `MlxWhisperEngine` (mlx-whisper, large-v3 / large-v3-turbo) behind the existing engine
   interface, automatic choice on Mac, CPU fallback, same project output; separation on MPS/CoreML.
4. **Rendering on Mac** — Blender detection + Cycles Metal/Eevee, VideoToolbox encoding, render presets tuned for M chips,
   RENDER_INSTRUCTIONS/DJ guide Mac notes.
5. **Mac integration** — fonts → ~/Library/Fonts, Resolve script folder check, Claude CLI on Mac, Open in Finder,
   verify_local Mac checks (MPS, MLX, Metal render, VideoToolbox) → REPORT_LOCAL.md.
6. **Full Mac test pass** — VERIFY_LOCAL Mac section + README Mac chapter.

## What I can and cannot check in the cloud
- Can: macOS GitHub runners on Apple Silicon run the unit + browser tests, the install script, the app bundle build
  and CPU paths (and probably MLX on the runner's M chip).
- Cannot: your Mac's real GPU speed, Gatekeeper prompts, Resolve/Blender GUIs, Rekordbox/Serato on Mac — those go in
  VERIFY_LOCAL (Mac section) and your REPORT_LOCAL.md, same loop as on Windows.

## Decisions (2026-11-16, from the user)
1. **Light `.app` + git Update now** (no self-contained Python bundle).
2. Test Mac: **MacBook Air, base model (8 GB RAM, fanless)** → defaults: Whisper **large-v3-turbo** (MLX), Eevee
   PREVIEW/DRAFT render presets suggested first, free Whisper memory before Blender starts.
3. **MLX Whisper** as the Mac engine (faster-whisper CPU int8 as fallback).
4. **Separate Mac release channel**: shared code is developed on `main` (Windows unchanged); Mac installs follow the
   branch **`mac-release`**, which is moved forward to `main` only after the macOS CI job passes.

## Questions before starting (answered above)
1. App style: lightweight `.app` that keeps the git **Update now** (recommended) — or a fully self-contained app with
   its own Python inside (bigger, no git needed, but updates mean downloading a new app each time)?
2. Do you have a Mac to test on (which chip and how much RAM)? 16 GB+ is comfortable for Whisper large-v3 + Blender.
3. Whisper on Mac: MLX (fastest on M chips, recommended) — OK to add it as a second engine?
4. Same repo + updater channel as Windows (recommended), or a separate Mac release branch?
