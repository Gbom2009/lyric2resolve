"""Phase 13: texture sync (fake network), license gate, verification, manifest/credits, custom, endpoints."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from lyric2resolve.assets import textures as tx


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()  # noqa: S324


JPG = b"\xff\xd8\xff" + b"x" * 100
HDR = b"#?RADIANCE\n" + b"y" * 100


def acg_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in ("Lava004_1K-JPG_Color.jpg", "Lava004_1K-JPG_NormalGL.jpg", "Lava004_1K-JPG_NormalDX.jpg",
                  "Lava004_1K-JPG_Roughness.jpg", "Lava004_1K-JPG_Emission.jpg", "Lava004.usdc", "../evil.jpg"):
            z.writestr(n, JPG)
    return buf.getvalue()


ZIP = acg_zip()


class FakeNet:
    def __init__(self, license_ok=True, bad_md5=False):
        self.license_ok, self.bad_md5 = license_ok, bad_md5
        self.downloads = []

    def text(self, url):
        return "All assets are CC0" if self.license_ok else "All rights reserved"

    def json(self, url):
        if url.endswith("/info/metal_plate"):
            return {"name": "Metal Plate", "authors": {"Rob Tuytel": "All"}}
        if url.endswith("/info/moonless_golf"):
            return {"name": "Moonless Golf", "authors": {"Greg Zaal": "All"}}
        if url.endswith("/files/metal_plate"):
            m = (lambda name: {"jpg": {"url": f"https://dl/{name}_1k.jpg", "size": len(JPG),
                                       "md5": "0" * 32 if self.bad_md5 else md5(JPG)}})
            return {"Diffuse": {"1k": m("metal_plate_diff")}, "nor_gl": {"1k": m("metal_plate_nor_gl")},
                    "Rough": {"1k": m("metal_plate_rough")}, "Displacement": {"1k": m("metal_plate_disp")}}
        if url.endswith("/files/moonless_golf"):
            return {"hdri": {"1k": {"hdr": {"url": "https://dl/moonless_golf_1k.hdr", "size": len(HDR), "md5": md5(HDR)}}}}
        if "ambientcg" in url:
            return {"foundAssets": [{"assetId": "Lava004", "displayName": "Lava 004", "shortLink": "https://ambientcg.com/a/Lava004",
                                     "downloadFolders": {"default": {"downloadFiletypeCategories": {"zip": {"downloads": [
                                         {"attribute": "1K-JPG", "fileName": "Lava004_1K-JPG.zip", "size": len(ZIP),
                                          "downloadLink": "https://acg/Lava004_1K-JPG.zip"}]}}}}}]}
        raise RuntimeError(url)

    def download(self, url, dest):
        self.downloads.append(url)
        dest.write_bytes(ZIP if url.endswith(".zip") else HDR if url.endswith(".hdr") else JPG)


CUR = {"polyhaven": [{"id": "metal_plate", "category": "sci-fi panels"}],
       "polyhaven_hdris": [{"id": "moonless_golf", "category": "dark hdri"}],
       "ambientcg": [{"id": "Lava004", "category": "lava"}]}


def test_curation_file():
    cur = tx.curation()
    assert len(cur["polyhaven"]) >= 5 and len(cur["polyhaven_hdris"]) >= 3 and len(cur["ambientcg"]) >= 10
    cats = {e["category"] for k in cur if not k.startswith("_") for e in cur[k]}
    for needed in ("brushed metal", "carbon fiber", "concrete", "cracked rock/lava-like", "sci-fi panels",
                   "grids/tiles", "fabric", "ice", "dark hdri"):
        assert needed in cats


def test_map_kind():
    assert tx.map_kind("Metal064_1K-JPG_Color.jpg") == "color"
    assert tx.map_kind("Metal064_1K-JPG_NormalDX.jpg") is None
    assert tx.map_kind("rusty_metal_02_nor_gl_1k.jpg") == "normal"
    assert tx.map_kind("x_Emission.jpg") == "emission"


def test_sync_manifest_credits_and_resume(tmp_path):
    net = FakeNet()
    rep = tx.sync(tmp_path, net, "1k", CUR, log=lambda m: None)
    assert rep.added == ["polyhaven/metal_plate", "polyhaven/moonless_golf", "ambientcg/Lava004"] and not rep.failed
    man = json.loads((tmp_path / "manifest.json").read_text())
    by = {a["id"]: a for a in man["assets"]}
    assert set(by["metal_plate"]["maps"]) == {"color", "normal", "roughness", "height"}
    assert by["moonless_golf"]["kind"] == "hdri" and by["moonless_golf"]["path"].endswith(".hdr")
    lava = by["Lava004"]
    assert set(lava["maps"]) == {"color", "normal", "roughness", "emission"}
    assert all(a["license"] == "CC0 1.0" for a in man["assets"])
    assert not (tmp_path / "evil.jpg").exists() and not list(tmp_path.rglob("*.usdc"))  # images only, no traversal
    assert "Rob Tuytel" in (tmp_path / "CREDITS.md").read_text()
    n = len(net.downloads)
    net2 = FakeNet()
    tx.sync(tmp_path, net2, "1k", CUR, log=lambda m: None)
    assert net2.downloads == []  # everything verified on disk -> nothing downloaded again
    assert n == 6


def test_license_gate_and_checksum(tmp_path):
    rep = tx.sync(tmp_path, FakeNet(license_ok=False), "1k", CUR, log=lambda m: None)
    assert len(rep.skipped_license) == 3 and not rep.added
    rep = tx.sync(tmp_path / "b", FakeNet(bad_md5=True), "1k", {"polyhaven": CUR["polyhaven"]}, log=lambda m: None)
    assert rep.failed and "checksum" in rep.failed[0]
    with pytest.raises(ValueError):
        tx.sync(tmp_path, FakeNet(), "8k", CUR)


def test_custom_textures(tmp_path):
    (tmp_path / "custom" / "my_metal").mkdir(parents=True)
    (tmp_path / "custom" / "my_metal" / "my_metal_basecolor.png").write_bytes(b"x")
    (tmp_path / "custom" / "my_metal" / "my_metal_normal.png").write_bytes(b"x")
    (tmp_path / "custom" / "sky.hdr").write_bytes(HDR)
    (tmp_path / "custom" / "photo.jpg").write_bytes(JPG)
    items = {a["id"]: a for a in tx.list_textures(tmp_path)}
    assert items["my_metal"]["maps"] == {"color": "custom/my_metal/my_metal_basecolor.png",
                                         "normal": "custom/my_metal/my_metal_normal.png"}
    assert items["sky"]["kind"] == "hdri" and items["photo"]["maps"]["color"] == "custom/photo.jpg"


def test_texture_endpoints(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lyric2resolve.editor.app import create_app

    tx.sync(tmp_path / "tex", FakeNet(), "1k", CUR, log=lambda m: None)
    c = TestClient(create_app(None, tmp_path / "projects", textures_root=tmp_path / "tex"))
    data = c.get("/api/textures").json()
    color = next(a for a in data["textures"] if a["id"] == "metal_plate")["maps"]["color"]
    assert c.get(f"/api/textures/file/{color}").content == JPG
    assert c.get("/api/textures/file/manifest.json").status_code == 404
    assert c.get("/api/textures/file/../../etc/passwd").status_code == 404
    assert c.get("/library").status_code == 200
