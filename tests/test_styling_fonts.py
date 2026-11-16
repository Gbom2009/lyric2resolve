"""Phase 9: style model, levels, section/block resolution, font sync (fake network), install."""

from __future__ import annotations

import json

import pytest

from lyric2resolve import project as proj
from lyric2resolve import styling
from lyric2resolve.assets import fonts

META_OFL = '''name: "Test Sans"
designer: "Jane Type"
license: "OFL"
category: "SANS_SERIF"
fonts {
  name: "Test Sans"
  style: "normal"
  weight: 400
  filename: "TestSans[wght].ttf"
  full_name: "Test Sans"
}
axes {
  tag: "wght"
}
'''
META_UFL = META_OFL.replace('license: "OFL"', 'license: "UFL"').replace("Test Sans", "Ubu")
CSS = '''@font-face {
  font-family: 'Test Sans';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/testsans/v1/a.ttf) format('truetype');
}
@font-face {
  font-family: 'Test Sans';
  font-style: normal;
  font-weight: 700;
  src: url(https://fonts.gstatic.com/s/testsans/v1/b.ttf) format('truetype');
}
'''
TTF = b"\x00\x01\x00\x00" + b"\x00" * 200


class FakeNet:
    def __init__(self, broken_font=False):
        self.calls = []
        self.broken_font = broken_font

    def __call__(self, url):
        self.calls.append(url)
        if "METADATA" in url:
            return (META_UFL if "/ubu/" in url else META_OFL).encode()
        if "css2" in url:
            return CSS.encode()
        if url.endswith(".ttf"):
            return b"<html>not a font" if self.broken_font else TTF
        raise RuntimeError(url)


ENTRIES = [{"family": "Test Sans", "repo_dir": "ofl/testsans", "category": "sans", "weights": [400, 700]},
           {"family": "Ubu", "repo_dir": "ufl/ubu", "weights": [400]}]


# ------------------------------------------------------------------ style model
def test_builtin_styles_are_valid():
    for name, s in styling.BUILTIN.items():
        s.validate()
        assert styling.TextStyle.from_dict(s.to_dict()) == s, name


def test_style_validation():
    with pytest.raises(styling.StyleError, match="colour"):
        styling.TextStyle.from_dict({"fill": "red"})
    with pytest.raises(styling.StyleError, match="between 0 and 1"):
        styling.TextStyle.from_dict({"position_y_16x9": 1.5})
    with pytest.raises(styling.StyleError, match="animation_in"):
        styling.TextStyle.from_dict({"animation_in": "explode"})
    with pytest.raises(styling.StyleError, match="invalid value"):
        styling.TextStyle.from_dict({"size_px": "big"})
    assert styling.TextStyle.from_dict({"size_px": "90", "unknown": 1}).size_px == 90


def make_project():
    words = proj.make_words([{"text": t, "start": i, "end": i + 0.5, "line": i // 2} for i, t in enumerate("a b c d".split())])
    p = proj.Project(words=words, blocks=proj.blocks_by_line(words),
                     sections=[proj.Section("s1", "verse", 0, 2), proj.Section("s2", "chorus", 2, 9)])
    return p


def test_resolution_order_and_levels():
    p = make_project()
    assert styling.style_for_block(p, p.blocks[1]).outline_width == 0  # project default level = BASIC
    p.settings.styling_level = "styled"
    styling.op_save_style(p, "Mine", {"fill": "#ff0000", "animation_in": "pop"})
    assert styling.style_for_block(p, p.blocks[1]).outline_width == 4.0  # default Clean
    styling.op_set_section_style(p, "Chorus", "Neon")
    assert styling.style_for_block(p, p.blocks[1]).glow_size > 0
    p.blocks[1].style = "Mine"
    s = styling.style_for_block(p, p.blocks[1])
    assert s.fill == "#ff0000" and s.animation_in == "none"  # STYLED: no animations
    assert styling.style_for_block(p, p.blocks[1], "full").animation_in == "pop"
    basic = styling.style_for_block(p, p.blocks[1], "basic")
    assert basic.fill == "#ffffff" and basic.outline_width == 0 and basic.animation_in == "none"
    styling.op_set_default_style(p, "Minimal")
    assert styling.style_for_block(p, p.blocks[0]).font_family == "Segoe UI"


def test_style_ops_errors_and_delete():
    p = make_project()
    with pytest.raises(styling.StyleError, match="built-in"):
        styling.op_save_style(p, "Neon", {})
    with pytest.raises(styling.StyleError, match="unknown"):
        styling.op_set_default_style(p, "Nope")
    styling.op_save_style(p, "Mine", {})
    styling.op_set_default_style(p, "Mine")
    styling.op_set_section_style(p, "verse", "Mine")
    p.blocks[0].style = "Mine"
    styling.op_delete_style(p, "Mine")
    book = styling.StyleBook.from_project(p.styles)
    assert book.default == styling.DEFAULT_STYLE and not book.by_section and p.blocks[0].style is None
    with pytest.raises(styling.StyleError):
        styling.op_delete_style(p, "Clean")
    with pytest.raises(styling.StyleError):
        styling.op_set_styling_level(p, "fancy")


def test_styles_roundtrip_in_project_json(tmp_path):
    p = make_project()
    styling.op_save_style(p, "Mine", {"fill": "#123456"})
    q = proj.load(proj.save(p, tmp_path / "p.json"))
    assert styling.StyleBook.from_project(q.styles).get("Mine").fill == "#123456"


def test_broken_user_preset_is_skipped():
    book = styling.StyleBook.from_project({"presets": {"Bad": {"fill": "nope"}, "Ok": {}}})
    assert "Ok" in book.presets and "Bad" not in book.presets


def test_editor_style_ops(tmp_path):
    from lyric2resolve.editor.app import EditorSession

    s = EditorSession(proj.save(make_project(), tmp_path / "project.json"))
    st = s.apply("save_style", {"name": "Mine", "style": {"fill": "#00ff00"}})
    assert st["styles"]["presets"]["Mine"]["fill"] == "#00ff00" and "Neon" in st["styles"]["builtin"]
    s.apply("set_styling_level", {"level": "full"})
    assert s.project.settings.styling_level == "full"
    from lyric2resolve.editor.ops import OpError

    with pytest.raises(OpError):
        s.apply("save_style", {"name": "X", "style": {"fill": "bad"}})


# ------------------------------------------------------------------ fonts
def test_parse_metadata_and_css():
    m = fonts.parse_metadata(META_OFL)
    assert m["name"] == "Test Sans" and m["license"] == "OFL" and m["designer"] == "Jane Type"
    assert m["fonts"][0]["filename"] == "TestSans[wght].ttf"
    faces = fonts.parse_css(CSS)
    assert [(f["weight"], f["url"][-5:]) for f in faces] == [(400, "a.ttf"), (700, "b.ttf")]


def test_curation_file_only_allowed_license_dirs():
    entries = fonts.curation()
    assert len(entries) >= 20
    assert all(e["repo_dir"].split("/")[0] in ("ofl", "apache") for e in entries)


def test_sync_license_filter_manifest_credits(tmp_path):
    net = FakeNet()
    rep = fonts.sync(tmp_path, fetch=net, families=ENTRIES, log=lambda m: None, delay_s=0)
    assert rep.added == ["Test Sans"] and len(rep.rejected) == 1 and "UFL" in rep.rejected[0]
    man = json.loads((tmp_path / "manifest.json").read_text())
    fam = man["families"][0]
    assert fam["license"] == "OFL" and len(fam["files"]) == 2
    assert (tmp_path / fam["files"][0]["path"]).read_bytes() == TTF
    credits = (tmp_path / "CREDITS.md").read_text()
    assert "Test Sans" in credits and "Jane Type" in credits and "Ubu" not in credits
    # second run: resumable, no font downloads again
    net2 = FakeNet()
    rep2 = fonts.sync(tmp_path, fetch=net2, families=ENTRIES[:1], log=lambda m: None, delay_s=0)
    assert rep2.skipped == ["Test Sans"] and not [u for u in net2.calls if u.endswith(".ttf")]


def test_sync_rejects_non_font_download(tmp_path):
    rep = fonts.sync(tmp_path, fetch=FakeNet(broken_font=True), families=ENTRIES[:1], log=lambda m: None, delay_s=0)
    assert rep.failed and "not a font" in rep.failed[0]


def test_list_fonts_and_install(tmp_path):
    fonts.sync(tmp_path, fetch=FakeNet(), families=ENTRIES[:1], log=lambda m: None, delay_s=0)
    (tmp_path / "custom").mkdir()
    (tmp_path / "custom" / "MyFont-Bold.otf").write_bytes(b"OTTO" + b"\0" * 50)
    listed = fonts.list_fonts(tmp_path)
    sources = {f["family"]: f["source"] for f in listed}
    assert sources["Test Sans"] == "library" and sources["MyFont"] == "custom" and sources["Arial"] == "system"

    class FakeReg:
        def __init__(self):
            self.values = {}

        def set(self, k, v):
            self.values[k] = v

    reg = FakeReg()
    target = tmp_path / "winfonts"
    names = fonts.install_fonts(tmp_path, target, reg, notify=lambda: None)
    assert sorted(names) == ["MyFont-Bold.otf", "TestSans-Bold.ttf", "TestSans-Regular.ttf"]
    assert reg.values["TestSans-Bold (TrueType)"] == str(target / "TestSans-Bold.ttf")
    assert reg.values["MyFont-Bold (OpenType)"].endswith("MyFont-Bold.otf")
    assert (target / "TestSans-Regular.ttf").exists()


def test_install_fonts_refuses_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows"):
        fonts.install_fonts(tmp_path, tmp_path / "t")


def test_font_api_endpoints(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import EditorSession, create_app

    fonts.sync(tmp_path / "fonts", fetch=FakeNet(), families=ENTRIES[:1], log=lambda m: None, delay_s=0)
    s = EditorSession(proj.save(make_project(), tmp_path / "project.json"))
    c = TestClient(create_app(s, fonts_root=tmp_path / "fonts"))
    listed = c.get("/api/fonts").json()["fonts"]
    lib = next(f for f in listed if f["source"] == "library")
    assert c.get(f"/api/fonts/file/{lib['files'][0]}").content == TTF
    assert c.get("/api/fonts/file/../project.json").status_code == 404
    assert c.get("/api/fonts/file/manifest.json").status_code == 404
