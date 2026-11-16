"""Updater logic tests with a temporary bare repo acting as the GitHub remote."""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

import pytest

from lyric2resolve import paths
from lyric2resolve.updater import changelog, core, messages, selfcopy
from lyric2resolve.updater.config import UpdaterConfig, UpdaterState, load_config, load_state, save_config, save_state
from lyric2resolve.updater.gitops import Git, GitError, classify_error

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}

OK_INIT = "__version__ = '0.0.1'\n"


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit(repo: Path, msg: str, files: dict[str, str]) -> str:
    for rel, text in files.items():
        write(repo, rel, text)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)
    return sh(repo, "rev-parse", "HEAD")


def changelog_text(*entries: tuple[str, str]) -> str:
    return "# Changelog\n\n" + "\n\n".join(f"## {h}\n{b}" for h, b in entries) + "\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for k, v in GIT_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "data"))


@pytest.fixture
def repos(tmp_path):
    """(remote bare, dev clone that pushes, user clone = installed copy)."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(remote), str(dev)], check=True, capture_output=True)
    sh(dev, "checkout", "-q", "-b", "main")
    commit(dev, "Initial", {
        "CHANGELOG.md": changelog_text(("Phase 1", "Launcher.")),
        "requirements/launcher.txt": "# none\n",
        "src/lyric2resolve/__init__.py": OK_INIT,
        "src/lyric2resolve/updater/__init__.py": "",
        "src/lyric2resolve/updater/core.py": "X = 1\n",
    })
    sh(dev, "push", "-q", "origin", "main")
    user = tmp_path / "user"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), str(user)], check=True, capture_output=True)
    return remote, dev, user


@pytest.fixture
def settings(tmp_path):
    d = tmp_path / "data" / "settings"
    d.mkdir(parents=True)
    return d


class FakeRunner:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, cmd, cwd):
        self.calls.append(cmd)
        if self.fail_on and any(self.fail_on in c for c in cmd):
            raise RuntimeError(f"boom: {self.fail_on}")


def pip_calls(runner: FakeRunner) -> list[list[str]]:
    return [c for c in runner.calls if "pip" in c or any("setup_update" in x for x in c)]


def push_update(dev: Path, msg="Phase 2 work", entry=("Phase 2", "New: settings."), extra=None) -> str:
    old = (dev / "CHANGELOG.md").read_text()
    files = {"CHANGELOG.md": old.replace("# Changelog\n\n", f"# Changelog\n\n## {entry[0]}\n{entry[1]}\n\n")}
    files.update(extra or {})
    sha = commit(dev, msg, files)
    sh(dev, "push", "-q", "origin", "main")
    return sha


# ------------------------------------------------------------------ pure logic
def test_classify():
    assert core.classify(0, 0) == core.UP_TO_DATE
    assert core.classify(0, 3) == core.BEHIND
    assert core.classify(2, 0) == core.AHEAD
    assert core.classify(1, 1) == core.DIVERGED


def test_changelog_new_entries():
    old = changelog_text(("Phase 1", "a"))
    new = changelog_text(("Phase 3", "c"), ("Phase 2", "b"), ("Phase 1", "a"))
    got = changelog.new_entries(old, new)
    assert [e.heading for e in got] == ["Phase 3", "Phase 2"]
    edited = changelog_text(("Phase 1", "a + fix"))
    assert [e.heading for e in changelog.new_entries(old, edited)] == ["Phase 1"]
    assert changelog.new_entries(None, None) == []
    assert "No new" in changelog.render_entries([])


def test_classify_error():
    assert classify_error("fatal: Authentication failed for 'https://github.com/x'") == "auth"
    assert classify_error("fatal: could not read Username for 'https://github.com'") == "auth"
    assert classify_error("Could not resolve host: github.com") == "offline"
    assert classify_error("something else") == "error"


def test_config_roundtrip_and_defaults(settings):
    assert load_config(settings) == UpdaterConfig()
    cfg = UpdaterConfig(branch="dev", check_at_login=True, fetch_timeout_s=1)
    save_config(cfg, settings)
    loaded = load_config(settings)
    assert loaded.branch == "dev" and loaded.check_at_login
    assert loaded.fetch_timeout_s == 3  # clamped
    (settings / "updater.json").write_text("{not json", encoding="utf-8")
    assert load_config(settings) == UpdaterConfig()
    (settings / "updater.json").write_text('{"branch": "x", "unknown": 1}', encoding="utf-8")
    assert load_config(settings).branch == "x"


def test_state_roundtrip(settings):
    save_state(UpdaterState(requirements_hash="abc"), settings)
    assert load_state(settings).requirements_hash == "abc"


def test_data_dir_conventions(tmp_path):
    assert paths.data_dir({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}, "win32") == \
        Path(r"C:\Users\x\AppData\Local") / "lyric2resolve"
    assert paths.data_dir({paths.DATA_ENV: str(tmp_path)}, "win32") == tmp_path
    assert paths.data_dir({"XDG_DATA_HOME": str(tmp_path)}, "linux") == tmp_path / "lyric2resolve"
    root = paths.ensure_data_dir(tmp_path / "d")
    assert (root / "projects").is_dir() and (root / "assets" / "textures" / "custom").is_dir()


def test_code_dir_is_repo_root():
    assert (paths.code_dir() / "pyproject.toml").exists()


def test_requirements_hash(tmp_path):
    req = tmp_path / "requirements" / "a.txt"
    req.parent.mkdir(parents=True)
    req.write_bytes(b"x\n")  # bytes: write_text would translate newlines on Windows
    h1 = core.requirements_hash(tmp_path)
    req.write_bytes(b"x\r\n")
    assert core.requirements_hash(tmp_path) == h1  # line endings don't count
    write(tmp_path, "pyproject.toml", "[project]\n")
    assert core.requirements_hash(tmp_path) != h1
    assert core.requirements_changed(tmp_path, UpdaterState(requirements_hash=h1))


def test_rollback_tag_name_sortable():
    a = core.make_rollback_tag(dt.datetime(2026, 1, 2, 3, 4, 5))
    b = core.make_rollback_tag(dt.datetime(2026, 1, 10, 0, 0, 0))
    assert a.startswith("l2r-rollback/") and sorted([b, a], reverse=True) == [b, a]


# ------------------------------------------------------------------ git checks
def test_up_to_date(repos):
    _, _, user = repos
    status = core.check_for_update(Git(user), UpdaterConfig())
    assert status.state == core.UP_TO_DATE and not status.update_available
    assert "up to date" in messages.status_line(status, "abc")


def test_behind_shows_changelog_and_commits(repos):
    _, dev, user = repos
    push_update(dev)
    status = core.check_for_update(Git(user), UpdaterConfig())
    assert status.state == core.BEHIND and status.behind == 1 and status.update_available
    assert [e.heading for e in status.changelog_entries] == ["Phase 2"]
    assert status.commits and "Phase 2 work" in status.commits[0]
    text = messages.update_available_text(status)
    assert "New: settings." in text and "Phase 2 work" in text


def test_ahead_and_diverged(repos):
    _, dev, user = repos
    commit(user, "local only", {"local.txt": "x"})
    assert core.check_for_update(Git(user), UpdaterConfig()).state == core.AHEAD
    push_update(dev)
    status = core.check_for_update(Git(user), UpdaterConfig())
    assert status.state == core.DIVERGED and status.update_available


def test_offline_fails_silently(repos):
    _, _, user = repos
    sh(user, "remote", "set-url", "origin", str(user.parent / "does-not-exist.git"))
    status = core.check_for_update(Git(user), UpdaterConfig(fetch_timeout_s=5))
    assert status.state in (core.OFFLINE, core.ERROR)
    assert not status.update_available


def test_fetch_timeout_is_offline(repos, monkeypatch):
    _, _, user = repos
    git = Git(user)

    def slow_fetch(*a, **k):
        raise GitError("timed out", kind="timeout")

    monkeypatch.setattr(git, "fetch", slow_fetch)
    assert core.check_for_update(git, UpdaterConfig()).state == core.OFFLINE


def test_refuses_unexpected_remote(repos):
    _, _, user = repos
    status = core.check_for_update(Git(user), UpdaterConfig(repo_url="https://github.com/someone/else"))
    assert status.state == core.ERROR and "Refusing" in status.message


def test_missing_git_binary(repos):
    _, _, user = repos
    status = core.check_for_update(Git(user, git_exe="git-does-not-exist-xyz"), UpdaterConfig())
    assert status.state == core.ERROR and "not installed" in status.message


# ------------------------------------------------------------------ update flow
def test_update_fast_forward(repos, settings):
    _, dev, user = repos
    git = Git(user)
    old = git.head()
    new = push_update(dev, extra={"requirements/core.txt": "numpy\n"})
    steps, runner = [], FakeRunner()
    result = core.run_update(git, UpdaterConfig(), settings, progress=lambda i, n, d: steps.append(i), runner=runner)
    assert result.ok, result.error
    assert git.head() == new and result.old == old
    assert sorted(set(steps)) == list(range(len(core.STEP_NAMES)))
    assert git.rev(result.rollback_tag) == old
    assert result.deps_installed and pip_calls(runner)
    assert [e.heading for e in result.changelog_entries] == ["Phase 2"]
    assert any("core.txt" in f for f in result.changed_files)
    text = messages.whats_changed_text(result)
    assert "New: settings." in text and "added: requirements/core.txt" in text
    assert load_state(settings).requirements_hash == core.requirements_hash(user)


def test_no_dependency_install_when_requirements_unchanged(repos, settings):
    _, dev, user = repos
    save_state(UpdaterState(requirements_hash=core.requirements_hash(user)), settings)
    push_update(dev)
    runner = FakeRunner()
    result = core.run_update(Git(user), UpdaterConfig(), settings, runner=runner)
    assert result.ok and not result.deps_installed and not pip_calls(runner)


def test_setup_update_script_used_when_present(repos, settings):
    _, dev, user = repos
    push_update(dev, extra={"scripts/setup_update.py": "print('x')\n", "requirements/gpu.txt": "torch\n"})
    runner = FakeRunner()
    assert core.run_update(Git(user), UpdaterConfig(), settings, runner=runner).ok
    assert any(any("setup_update.py" in x for x in c) and "--update" in c for c in runner.calls)


def test_dirty_tree_refused(repos, settings):
    _, dev, user = repos
    push_update(dev)
    git = Git(user)
    old = git.head()
    write(user, "src/lyric2resolve/updater/core.py", "X = 2  # my edit\n")
    result = core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner())
    assert not result.ok and "modified locally" in result.error and "core.py" in result.error
    assert git.head() == old and not git.rollback_tags()
    assert (user / "src/lyric2resolve/updater/core.py").read_text() == "X = 2  # my edit\n"


def test_untracked_files_do_not_block(repos, settings):
    _, dev, user = repos
    push_update(dev)
    write(user, "notes-of-user.txt", "hi")
    assert core.run_update(Git(user), UpdaterConfig(), settings, runner=FakeRunner()).ok


def test_diverged_update_hard_resets(repos, settings):
    _, dev, user = repos
    local = commit(user, "local only", {"local.txt": "x"})
    new = push_update(dev)
    git = Git(user)
    result = core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner())
    assert result.ok and git.head() == new
    assert git.rev(result.rollback_tag) == local  # local commit stays recoverable


def test_failed_dependency_step_rolls_back(repos, settings):
    _, dev, user = repos
    git = Git(user)
    old = git.head()
    push_update(dev, extra={"requirements/core.txt": "broken\n"})
    result = core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner(fail_on="pip"))
    assert not result.ok and result.rolled_back
    assert result.failed_step == core.STEP_NAMES[3]
    assert git.head() == old
    assert "automatically restored" in messages.failure_text(result)


def test_broken_self_check_rolls_back_with_real_runner(repos, settings):
    _, dev, user = repos
    git = Git(user)
    old = git.head()
    save_state(UpdaterState(requirements_hash=core.requirements_hash(user)), settings)
    push_update(dev, extra={"src/lyric2resolve/__init__.py": "raise ImportError('broken release')\n"})
    result = core.run_update(git, UpdaterConfig(), settings)  # default runner -> real python import
    assert not result.ok and result.failed_step == core.STEP_NAMES[5]
    assert "broken release" in result.error
    assert result.rolled_back and git.head() == old


def test_successful_self_check_with_real_runner(repos, settings):
    _, dev, user = repos
    save_state(UpdaterState(requirements_hash=core.requirements_hash(user)), settings)
    push_update(dev)
    assert core.run_update(Git(user), UpdaterConfig(), settings).ok


def test_fetch_failure_does_not_touch_anything(repos, settings):
    _, dev, user = repos
    push_update(dev)
    git = Git(user)
    old = git.head()
    sh(user, "remote", "set-url", "origin", str(user.parent / "gone.git"))
    result = core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner())
    assert not result.ok and result.failed_step == core.STEP_NAMES[0] and git.head() == old


def test_prune_rollback_tags(repos, settings):
    _, dev, user = repos
    git = Git(user)
    for i in range(4):
        push_update(dev, msg=f"c{i}", entry=(f"Phase {i + 2}", "x"))
        assert core.run_update(git, UpdaterConfig(keep_rollback_tags=2), settings, runner=FakeRunner(),
                               now=dt.datetime(2026, 1, 1, 0, 0, i)).ok
    assert len(git.rollback_tags()) == 2


# ------------------------------------------------------------------ rollback
def test_manual_rollback_steps_back_one_version_at_a_time(repos, settings):
    _, dev, user = repos
    git = Git(user)
    v1 = git.head()
    push_update(dev, msg="v2", entry=("Phase 2", "b"))
    assert core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner(), now=dt.datetime(2026, 1, 1)).ok
    v2 = git.head()
    push_update(dev, msg="v3", entry=("Phase 3", "c"))
    assert core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner(), now=dt.datetime(2026, 1, 2)).ok
    r = core.rollback(git, settings, runner=FakeRunner())
    assert r.ok and git.head() == v2
    assert "Rolled back" in messages.rollback_text(r)
    r = core.rollback(git, settings, runner=FakeRunner())
    assert r.ok and git.head() == v1
    # the newer version is offered again as an update
    assert core.check_for_update(git, UpdaterConfig()).state == core.BEHIND


def test_rollback_without_previous_version(repos, settings):
    _, _, user = repos
    r = core.rollback(Git(user), settings, runner=FakeRunner())
    assert not r.ok and "no previous version" in r.error


def test_rollback_refuses_dirty_tree(repos, settings):
    _, dev, user = repos
    git = Git(user)
    push_update(dev)
    assert core.run_update(git, UpdaterConfig(), settings, runner=FakeRunner()).ok
    write(user, "CHANGELOG.md", "edited")
    r = core.rollback(git, settings, runner=FakeRunner())
    assert not r.ok and "modified locally" in r.error


# ------------------------------------------------------------------ self copy / login entry
def test_copy_updater_to_temp_and_import(tmp_path):
    src_pkg = paths.code_dir() / "src" / "lyric2resolve"
    root = selfcopy.copy_updater(src_pkg, tmp_path / "copy")
    assert (root / "lyric2resolve" / "updater" / "core.py").exists()
    assert (root / "lyric2resolve" / "paths.py").exists()
    cmd, env = selfcopy.apply_command(root, tmp_path / "repo")
    assert cmd[1:4] == ["-m", "lyric2resolve.updater", "apply-update"] and env["PYTHONPATH"] == str(root)
    # the copy is self-contained: importable without the code folder
    out = subprocess.run([cmd[0].replace("pythonw", "python"), "-I", "-c",
                          "import sys; sys.path.insert(0, sys.argv[1]); import lyric2resolve.updater.core as c, "
                          "lyric2resolve.updater.cli; print(c.__file__)", str(root)],
                         capture_output=True, text=True, check=True).stdout
    assert str(root) in out


def test_login_check_entry(tmp_path):
    folder = tmp_path / "Startup"
    target = selfcopy.set_login_check(True, tmp_path / "repo", folder)
    text = target.read_text(encoding="utf-8")
    assert "launcher.pyw" in text and "--login-check" in text
    selfcopy.set_login_check(False, tmp_path / "repo", folder)
    assert not target.exists()
    assert selfcopy.startup_folder({"APPDATA": str(tmp_path)}).name == "Startup"


def test_cli_version_and_check(repos, capsys):
    from lyric2resolve.updater.cli import main

    _, dev, user = repos
    assert main(["--repo", str(user), "version"]) == 0
    push_update(dev)
    assert main(["--repo", str(user), "check-update"]) == 0
    out = capsys.readouterr().out
    assert "update is available" in out and "New: settings." in out


# ------------------------------------------------------------------ UI smoke (needs Tk + a display; xvfb in CI)
@pytest.fixture(scope="module")
def tk_root():
    """One shared Tk interpreter for all UI tests (creating many in one process is flaky on Windows)."""
    import os
    import sys

    tk = pytest.importorskip("tkinter")
    if not sys.platform.startswith("win") and not os.environ.get("DISPLAY"):
        pytest.skip("no display")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not usable: {exc}")
    root.withdraw()
    yield root
    root.destroy()


def _pump(win, cond, timeout=20.0):
    import time

    end = time.time() + timeout
    while time.time() < end and not cond():
        win.root.update()
        time.sleep(0.02)
    return cond()


def test_ui_launcher_and_apply_windows(repos, settings, monkeypatch, tk_root):
    from lyric2resolve.updater import ui

    _, dev, user = repos
    save_state(UpdaterState(requirements_hash=core.requirements_hash(user)), settings)
    push_update(dev)
    shown = []
    monkeypatch.setattr(ui.LauncherWindow, "show_update", lambda self, s: shown.append(s))
    win = ui.LauncherWindow(user, master=tk_root)
    assert _pump(win, lambda: bool(shown)) and shown[0].update_available
    win.root.destroy()

    results = []
    monkeypatch.setattr(ui.ApplyWindow, "show_result", lambda self, r: results.append(r))
    app = ui.ApplyWindow(user, master=tk_root)
    assert _pump(app, lambda: bool(results))
    assert results[0].ok, results[0].error
    app.root.destroy()


def test_ui_screens_render(repos, settings, tk_root):
    from lyric2resolve.updater import ui

    _, dev, user = repos
    push_update(dev)
    win = ui.LauncherWindow(user, skip_check=True, master=tk_root)
    win.show_update(core.check_for_update(Git(user), UpdaterConfig()))
    win.root.update()
    win.show_status(core.UpdateStatus(core.OFFLINE, message="Offline"))
    win.root.update()
    # reuse the window to render both result screens of the apply window
    win._finish = win.root.destroy
    ui.ApplyWindow.show_result(win, core.UpdateResult(ok=True, rollback_tag="l2r-rollback/x"))
    win.root.update()
    ui.ApplyWindow.show_result(win, core.UpdateResult(ok=False, failed_step="Fetch", error="x"))
    win.root.update()
    win.root.destroy()
