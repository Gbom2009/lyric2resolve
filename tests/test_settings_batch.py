"""Phase 18: branding/theme, settings API, update banner hand-off, batch mode."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from lyric2resolve import branding, paths
from lyric2resolve import project as proj
from lyric2resolve.settings import AppSettings, load_settings, save_settings
from lyric2resolve.updater import appctl

REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ branding
def test_repo_brand_file_is_valid():
    b = branding.load_brand()
    assert b.name == "Team Funqtion" and b.colors["accent"] == "#f68712" and b.colors["page"] == "#040404"
    assert (REPO / "src" / "lyric2resolve" / "editor" / "static" / b.logo).is_file()
    from lyric2resolve.styling import TextStyle

    TextStyle.from_dict(b.video_text_style)  # the brand text style is a valid style preset


def test_user_brand_copy_wins_and_broken_falls_back(tmp_path):
    data = json.loads((REPO / "config" / branding.BRAND_FILE).read_text(encoding="utf-8"))
    data["colors"]["accent"] = "#123456"
    branding.user_brand_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    branding.user_brand_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    assert branding.load_brand(settings_dir=tmp_path).colors["accent"] == "#123456"
    on = AppSettings(funqtion_branding=True)
    assert "#123456" in branding.current_css(on, tmp_path)
    data["colors"]["accent"] = "orange"
    branding.user_brand_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(branding.BrandError):
        branding.load_brand(settings_dir=tmp_path)
    assert "branding off" in branding.current_css(on, tmp_path)


def test_theme_css_default_and_branded():
    assert branding.current_css(AppSettings()).startswith("/* default theme")
    assert branding.branding_on(AppSettings(theme="funqtion"))
    fonts = [{"family": "Archivo Black", "source": "library", "files": ["ArchivoBlack/ArchivoBlack-Regular.ttf"]},
             {"family": "JetBrains Mono", "source": "library",
              "files": ["JetBrainsMono/JetBrainsMono-Light.ttf", "JetBrainsMono/JetBrainsMono-BoldItalic.ttf"]},
             {"family": "Arial", "source": "system", "files": []}]
    css = branding.current_css(AppSettings(funqtion_branding=True), fonts=fonts)
    assert "--accent: #f68712" in css and "--bg: #040404" in css and "--sung: #f68712" in css
    assert "/static/brand/funqtion-logo.svg" in css and "'JetBrains Mono'" in css
    assert "url('/api/fonts/file/JetBrainsMono/JetBrainsMono-Light.ttf'); font-weight: 300; font-style: normal" in css
    assert "font-weight: 700; font-style: italic" in css and css.count("@font-face") == 3
    assert branding._mix("#000000", "#ffffff", 0.5) == "#808080"


# ------------------------------------------------------------------ launcher hand-off
def test_update_request_handoff(tmp_path):
    assert not appctl.take_update_request(tmp_path)
    appctl.request_update(tmp_path)
    assert appctl.take_update_request(tmp_path)
    assert not appctl.take_update_request(tmp_path)  # only once
    p = appctl.request_update(tmp_path)
    old = time.time() - 3600
    import os

    os.utime(p, (old, old))
    assert not appctl.take_update_request(tmp_path) and not p.exists()  # stale requests are dropped
    assert appctl.app_env(REPO)[appctl.LAUNCHER_ENV] == "1"


# ------------------------------------------------------------------ settings API
@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import EditorSession, create_app
    from lyric2resolve.editor.settings_api import UpdateChecker
    from tests.e2e.conftest import make_project

    checks = {"n": 0, "result": {"state": "up_to_date", "update_available": False, "version": "abc1234 (2026-11-16)"}}

    def fake_check():
        checks["n"] += 1
        return dict(checks["result"])

    sdir = tmp_path / "settings"
    path = make_project(tmp_path)
    app = create_app(EditorSession(path), path.parents[1], settings_dir=sdir,
                     update_checker=UpdateChecker(settings_dir=sdir, check=fake_check))
    c = TestClient(app)
    c.checks, c.sdir = checks, sdir
    return c


def test_settings_get_put(client):
    d = client.get("/api/settings").json()
    assert d["settings"]["default_fps"] == 25.0 and 29.97 in d["choices"]["fps"]
    assert set(d["detected"]) >= {"ffmpeg", "blender", "claude", "gpu"}
    assert d["brand"]["name"] == "Team Funqtion" and d["updater"]["branch"] == "main"
    r = client.put("/api/settings", json={"default_fps": 29.97, "layouts": ["9:16"], "funqtion_branding": True})
    assert r.status_code == 200 and r.json()["settings"]["layouts"] == ["9:16"]
    s, _ = load_settings(client.sdir)
    assert s.default_fps == 29.97 and s.funqtion_branding
    r = client.put("/api/settings", json={"default_fps": 31})
    assert r.status_code == 200 and r.json()["warnings"] and load_settings(client.sdir)[0].default_fps == 25.0
    assert client.put("/api/settings", json={"hack": 1}).status_code == 400
    assert client.put("/api/settings", json={"extra": {}}).status_code == 400
    assert "settings" in client.get("/api/settings?probe=false").json()


def test_updater_settings(client):
    r = client.put("/api/settings/updater", json={"check_at_launch": False, "check_at_login": True})
    assert r.status_code == 200 and not r.json()["updater"]["check_at_launch"] and "login-check on" in r.json()["note"]
    from lyric2resolve.updater.config import load_config

    assert load_config(client.sdir).check_at_login
    assert client.put("/api/settings/updater", json={"repo_url": "https://evil"}).status_code == 400


def test_theme_css_and_pages(client):
    assert client.get("/theme.css").text.startswith("/* default theme")
    client.put("/api/settings", json={"funqtion_branding": True})
    css = client.get("/theme.css")
    assert css.headers["content-type"].startswith("text/css") and "#f68712" in css.text
    assert client.get("/settings").status_code == 200
    for page in ("/", "/library", "/ideas", "/karaoke", "/settings"):
        assert "/theme.css" in client.get(page).text
    assert client.get("/static/brand/funqtion-logo.svg").status_code == 200
    b = client.get("/api/brand").json()
    r = client.post("/api/op/save_style", json={"name": b["name"], "style": b["video_text_style"]})
    assert r.status_code == 200 and "Team Funqtion" in r.json()["styles"]["presets"]


def test_update_banner_api(client, monkeypatch):
    monkeypatch.delenv("L2R_NO_UPDATE_CHECK")
    checker = client.app.state.update_checker
    checker.status(refresh=True, wait=5)
    st = client.get("/api/update/status").json()
    assert st["state"] == "up_to_date" and not st["checking"] and not st["via_launcher"]
    assert client.post("/api/update/request").status_code == 409  # nothing to update
    client.checks["result"] = {"state": "behind", "behind": 2, "update_available": True, "changelog": "## Phase 18",
                               "commits": ["abc Phase 18"]}
    checker.status(refresh=True, wait=5)
    r = client.post("/api/update/request")
    assert r.status_code == 409 and "launcher" in r.json()["detail"]  # editor not started by the launcher
    monkeypatch.setenv("L2R_LAUNCHER", "1")
    r = client.post("/api/update/request")
    assert r.status_code == 200 and appctl.take_update_request(client.sdir)
    n = client.checks["n"]
    client.get("/api/update/status")  # cached: no new check within 30 minutes
    assert client.checks["n"] == n


def test_update_checker_never_raises(tmp_path, monkeypatch):
    from lyric2resolve.editor.settings_api import UpdateChecker

    monkeypatch.delenv("L2R_NO_UPDATE_CHECK")
    st = UpdateChecker(repo=tmp_path, settings_dir=tmp_path).status(refresh=True, wait=20)
    assert st["state"] in ("error", "offline") and not st["checking"]
    monkeypatch.setenv("L2R_NO_UPDATE_CHECK", "1")
    assert UpdateChecker(repo=tmp_path).status()["state"] == "disabled"


# ------------------------------------------------------------------ batch
def test_find_jobs_pairs_by_name(tmp_path):
    from lyric2resolve import batch

    names = ["One.mp3", "One (Acapella).wav", "Two - acapella.flac", "Two.wav", "Three.m4a", "Four.wav",
             "Four_vocals.wav", "notes.pdf"]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "Three.txt").write_text("la la", encoding="utf-8")
    jobs = {j.title: j for j in batch.find_jobs(tmp_path)}
    assert set(jobs) == {"One", "Two", "Three", "Four"}
    assert Path(jobs["One"].acapella).name == "One (Acapella).wav"
    assert Path(jobs["Two"].acapella).name == "Two - acapella.flac"
    assert Path(jobs["Four"].acapella).name == "Four_vocals.wav"
    assert jobs["Three"].acapella is None and Path(jobs["Three"].lyrics).name == "Three.txt"


def test_load_queue(tmp_path):
    from lyric2resolve import batch

    q = tmp_path / "q" / "queue.yaml"
    q.parent.mkdir()
    q.write_text("jobs:\n  - song: a.mp3\n    acapella: a_vox.wav\n    name: Alpha\n  - song: b.wav\n", encoding="utf-8")
    jobs = batch.jobs_from(q)
    assert jobs[0].title == "Alpha" and Path(jobs[0].acapella) == (q.parent / "a_vox.wav").resolve()
    assert jobs[1].acapella is None
    q.write_text("jobs:\n  - acapella: x.wav\n", encoding="utf-8")
    with pytest.raises(ValueError):
        batch.jobs_from(q)
    with pytest.raises(ValueError):
        batch.jobs_from(tmp_path / "x.txt")


def copy_ffmpeg():
    from lyric2resolve.audio import Ffmpeg

    def runner(cmd):
        shutil.copyfile(cmd[cmd.index("-i") + 1], cmd[-1])
        return 0, ""

    return Ffmpeg(runner=runner)


def test_batch_smoke(tmp_path):
    """Two songs through the whole pipeline (fake Whisper, real analysis + export); one broken job."""
    from lyric2resolve import batch
    from lyric2resolve.audio import wavio
    from lyric2resolve.transcription import FakeEngine

    sr = 44100
    t = np.arange(int(14 * sr)) / sr
    beat = (np.sin(2 * np.pi * 110 * t) * (np.mod(t, 0.5) < 0.08)).astype(np.float32) * 0.5
    vocal = (np.sin(2 * np.pi * 330 * t) * ((t > 1) & (t < 9))).astype(np.float32) * 0.3
    src = tmp_path / "songs"
    wavio.write(src / "Alpha.wav", np.stack([beat + vocal] * 2, axis=1), sr)
    wavio.write(src / "Alpha (acapella).wav", np.stack([vocal] * 2, axis=1), sr)
    (src / "Alpha.txt").write_text("we sing this song\nall night long\n", encoding="utf-8")
    secs = tmp_path / "sections.yaml"
    secs.write_text("default: word\n", encoding="utf-8")
    jobs = batch.find_jobs(src)
    jobs[0].sections = str(secs)
    jobs.append(batch.BatchJob(str(src / "Missing.wav"), str(src / "Alpha (acapella).wav"), name="Broken"))
    logs = []
    out = tmp_path / "out"
    results = batch.run_batch(jobs, out, settings=AppSettings(layouts=["16:9"]), engine=FakeEngine(),
                              ffmpeg=copy_ffmpeg(), cache_dir=tmp_path / "cache", formats=["fcpxml", "srt_csv_edl"],
                              log=logs.append)
    ok, bad = results
    assert ok.ok and not bad.ok and "not found" in bad.error.lower()
    p = proj.load(Path(ok.project))
    assert len(p.words) == 7 and len(p.blocks) == 7  # sections.yaml: one word per block
    assert p.analysis.get("bpm") and {w.line for w in p.words} == {0, 1}
    assert any(f.endswith(".fcpxml") for f in ok.files) and any(f.endswith(".srt") for f in ok.files)
    report = (out / "batch_report.md").read_text(encoding="utf-8")
    assert "1 of 2 songs done" in report and "Broken" in report
    assert any("=== 2/2" in m for m in logs)


def test_batch_cli_dry_run(tmp_path, capsys):
    from lyric2resolve.__main__ import main

    (tmp_path / "Song.wav").write_bytes(b"x")
    (tmp_path / "Song vocals.wav").write_bytes(b"x")
    assert main(["batch", str(tmp_path), "--dry-run"]) == 0
    assert "Song: song=Song.wav, acapella=Song vocals.wav" in capsys.readouterr().out
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["batch", str(empty)]) == 1


def test_parallel_settings_saves_never_lose_a_change(client):
    """CI caught it: two quick changes on the Settings page raced on one temp file and one change was lost."""
    import concurrent.futures

    keys = [{"default_fps": 29.97}, {"funqtion_branding": True}, {"width": 1280}, {"height": 720},
            {"language": "nl"}, {"whisper_model": "medium"}]
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda b: client.put("/api/settings", json=b).status_code, keys * 3))
    assert set(codes) == {200}
    s, _ = load_settings(client.sdir)
    assert (s.default_fps, s.funqtion_branding, s.width, s.height, s.language, s.whisper_model) == \
        (29.97, True, 1280, 720, "nl", "medium")
    assert not list(client.sdir.glob("*.tmp"))


def test_atomic_write_text(tmp_path):
    import concurrent.futures

    f = tmp_path / "a" / "x.json"
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda i: paths.atomic_write_text(f, f"value {i}"), range(40)))
    assert f.read_text().startswith("value ") and [p.name for p in f.parent.iterdir()] == ["x.json"]
