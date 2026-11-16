"""'New project' from the browser: uploaded song (+ acapella, lyrics) -> the full pipeline in the background.

The files are copied into `<projects>/<name>/input/`, then `batch.run_song` converts, checks alignment,
transcribes (or aligns the lyrics), analyses and builds the blocks. The browser polls the progress and opens
the project when it is done. One job at a time.
"""


import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import BinaryIO, Callable

DEPS_HELP = ("Transcription is not installed yet. Close the editor, open the lyric2resolve launcher and click "
             "'Run setup' (installs Whisper + PyTorch), then try again.")
BROKEN_TORCH_HELP = ("PyTorch is installed but broken ({detail}). This happens when torch and torchaudio come from "
                     "different builds (CUDA vs CPU). Fix: close the editor, open the lyric2resolve launcher and click "
                     "'Update now' (or run setup_windows.bat): setup now detects this and reinstalls a matching set.")


def unique_folder(projects_dir: Path, name: str) -> tuple[str, Path]:
    from lyric2resolve.export import safe_name

    base = (name or "").strip() or "Untitled"
    title, n = base, 2
    while (Path(projects_dir) / safe_name(title)).exists():
        title = f"{base} ({n})"
        n += 1
    return title, Path(projects_dir) / safe_name(title)


def save_upload(src: BinaryIO, folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    clean = Path(filename or "audio").name.replace("..", "_") or "audio"
    dst = folder / clean
    with open(dst, "wb") as f:
        shutil.copyfileobj(src, f, 1024 * 1024)
    return dst


def default_engine(model: str | None, language: str | None):
    try:
        import faster_whisper  # noqa: F401
        import stable_whisper  # noqa: F401
    except ImportError as exc:
        if getattr(exc, "name", "") in ("faster_whisper", "stable_whisper", "torch"):
            raise RuntimeError(DEPS_HELP) from exc
        raise RuntimeError(BROKEN_TORCH_HELP.format(detail=exc)) from exc
    except OSError as exc:  # e.g. "Could not load this library: ...libtorchaudio.pyd"
        raise RuntimeError(BROKEN_TORCH_HELP.format(detail=exc)) from exc
    from lyric2resolve.transcription import engine_from_settings

    return engine_from_settings(model or None, language or None)


def default_ffmpeg():
    from lyric2resolve.audio import Ffmpeg
    from lyric2resolve.settings import load_settings
    from lyric2resolve.setup_tools import FFMPEG_HELP, find_tool

    exe = find_tool("ffmpeg", load_settings()[0].ffmpeg_path)
    if not exe:
        raise RuntimeError(FFMPEG_HELP)
    return Ffmpeg(str(exe))


class NewProjectJobs:
    def __init__(self, projects_dir: Path, engine_factory: Callable | None = None,
                 ffmpeg_factory: Callable | None = None, settings_dir: Path | None = None):
        self.projects_dir = Path(projects_dir)
        self.engine_factory = engine_factory or default_engine
        self.ffmpeg_factory = ffmpeg_factory or default_ffmpeg
        self.settings_dir = settings_dir
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict = {"running": False, "done": False, "log": []}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def prepare(self, name: str) -> tuple[str, Path]:
        """Reserve a project folder; uploads go into <folder>/input."""
        if self.running():
            raise RuntimeError("a new project is already being made - wait until it is finished")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        title, folder = unique_folder(self.projects_dir, name)
        (folder / "input").mkdir(parents=True)
        return title, folder

    def start(self, title: str, song: Path, acapella: Path | None = None, lyrics: str | None = None,
              language: str = "", granularity: str | None = None, model: str = "") -> dict:
        from lyric2resolve import batch
        from lyric2resolve import paths
        from lyric2resolve.settings import load_settings

        if self.running():
            raise RuntimeError("a new project is already being made - wait until it is finished")
        lyr_path = None
        if lyrics and lyrics.strip():
            lyr_path = Path(song).parent / "lyrics.txt"
            lyr_path.write_text(lyrics, encoding="utf-8")
        job = batch.BatchJob(str(song), str(acapella) if acapella else None, str(lyr_path) if lyr_path else None,
                             name=title)
        with self._lock:
            self._state = {"running": True, "done": False, "ok": False, "title": title, "project": "",
                           "error": "", "log": [], "started": time.time()}

        def log(msg: str) -> None:
            with self._lock:
                self._state["log"] = (self._state["log"] + [str(msg)])[-50:]

        def work() -> None:
            try:
                s, _ = load_settings(self.settings_dir)
                log("Checking ffmpeg…")
                ff = self.ffmpeg_factory()
                log("Loading Whisper (the first time it downloads the model, ~3 GB - this can take a while)…"
                    if not lyr_path else "Loading Whisper for lyric alignment (first time: model download)…")
                engine = self.engine_factory(model, language)
                if not acapella:
                    log("No acapella: separating the vocals from the song (slow, cached afterwards)…")
                res = batch.run_song(job, self.projects_dir, settings=s, engine=engine, ffmpeg=ff,
                                     cache_dir=paths.ensure_data_dir() / "cache", granularity=granularity,
                                     do_export=False, log=log)
                for m in res.messages:
                    if m and not m.startswith("Traceback"):
                        log(m.splitlines()[0])
                with self._lock:
                    self._state.update(ok=res.ok, project=res.project, error=res.error)
            except Exception as exc:  # shown in the dialog
                with self._lock:
                    self._state.update(ok=False, error=str(exc) or traceback.format_exc(limit=2))
            finally:
                with self._lock:
                    failed = not self._state.get("ok")
                    self._state.update(running=False, done=True)
                folder = Path(song).parent.parent
                if failed and folder.parent == self.projects_dir and not (folder / "project.json").exists():
                    shutil.rmtree(folder, ignore_errors=True)  # no half-made projects / "(2)", "(3)" names

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self.status()

    def status(self) -> dict:
        with self._lock:
            return {**self._state, "log": list(self._state.get("log", []))}

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread:
            self._thread.join(timeout)
        return not self.running()


def register(app, jobs_getter: Callable[[], NewProjectJobs], on_done_open: Callable[[Path], dict]) -> None:
    from fastapi import File, Form, HTTPException, UploadFile

    @app.post("/api/projects/new")
    def new_project(name: str = Form(""), song: UploadFile = File(...), acapella: UploadFile | None = File(None),
                    lyrics: str = Form(""), language: str = Form(""), granularity: str = Form("")):
        jobs = jobs_getter()
        from lyric2resolve.audio.convert import SUPPORTED

        for up in (song, acapella):
            if up is not None and up.filename and Path(up.filename).suffix.lower() not in SUPPORTED:
                raise HTTPException(status_code=400, detail=f"{up.filename}: use one of {', '.join(SUPPORTED)}")
        try:
            title, folder = jobs.prepare(name or Path(song.filename or "song").stem)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        song_path = save_upload(song.file, folder / "input", song.filename or "song.wav")
        aca_path = None
        if acapella is not None and acapella.filename:
            aca_path = save_upload(acapella.file, folder / "input" / "acapella", acapella.filename)
        gran = granularity if granularity in ("word", "line", "phrase", "auto") else None
        return jobs.start(title, song_path, aca_path, lyrics, language.strip(), gran)

    @app.get("/api/projects/new/status")
    def new_project_status():
        return jobs_getter().status()

    @app.post("/api/projects/new/open")
    def new_project_open():
        st = jobs_getter().status()
        if not st.get("ok") or not st.get("project"):
            raise HTTPException(status_code=409, detail=st.get("error") or "the new project is not ready")
        return on_done_open(Path(st["project"]))
