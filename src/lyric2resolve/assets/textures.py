"""CC0 texture + HDRI library: curated sync from Poly Haven and ambientCG, manifest, credits, browser listing.

APIs (checked 2026-11-16, no keys needed):
- Poly Haven: https://api.polyhaven.com/info/<id>, /files/<id> (per map + resolution: url, size, md5)
- ambientCG:  https://ambientcg.com/api/v2/full_json?id=<id>&include=downloadData (zip per resolution, size)
Both publish all assets as CC0; the license is confirmed from each site's license page during sync and
recorded per asset. Downloads are polite (one at a time, pauses), resumable (HTTP Range + per-asset manifest
updates) and verified (md5 for Poly Haven, size + zip integrity for ambientCG). Runs on the user's PC.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from lyric2resolve import paths

PH_API = "https://api.polyhaven.com"
ACG_API = "https://ambientcg.com/api/v2/full_json"
LICENSE_PAGES = {"polyhaven": "https://polyhaven.com/license", "ambientcg": "https://ambientcg.com/license"}
LICENSE = "CC0 1.0"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
USER_AGENT = "lyric2resolve-asset-sync/1 (personal use; polite)"
RESOLUTIONS = ("1k", "2k", "4k")
PH_MAPS = {"Diffuse": "color", "nor_gl": "normal", "Rough": "roughness", "Displacement": "height", "AO": "ao",
           "Metal": "metalness"}
MAP_TOKENS = {"color": {"color", "col", "albedo", "diffuse", "diff", "basecolor"},
              "normal": {"normalgl", "norgl", "normal", "nrm", "nor"},
              "roughness": {"roughness", "rough"}, "height": {"displacement", "height", "disp"},
              "ao": {"ambientocclusion", "ao", "occlusion"}, "metalness": {"metalness", "metallic"},
              "emission": {"emission", "emissive", "emit"}}
DX_NORMAL = {"normaldx", "nordx"}
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".exr", ".tif", ".tiff", ".hdr")


class Net(Protocol):
    def json(self, url: str) -> dict: ...
    def text(self, url: str) -> str: ...
    def download(self, url: str, dest: Path) -> None: ...


class HttpNet:
    def __init__(self, delay_s: float = 0.4, timeout: float = 60):
        self.delay, self.timeout = delay_s, timeout

    def _req(self, url: str, headers: dict | None = None):
        time.sleep(self.delay)  # polite rate limit
        h = {"User-Agent": USER_AGENT}
        h.update(headers or {})
        return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=self.timeout)

    def json(self, url: str) -> dict:
        with self._req(url) as r:
            return json.loads(r.read().decode("utf-8"))

    def text(self, url: str) -> str:
        with self._req(url) as r:
            return r.read().decode("utf-8", "replace")

    def download(self, url: str, dest: Path) -> None:
        """Resumable download into dest (via dest.part + HTTP Range)."""
        part = dest.with_name(dest.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        with self._req(url, headers) as r:
            mode = "ab" if have and getattr(r, "status", 200) == 206 else "wb"
            with open(part, mode) as fh:
                shutil.copyfileobj(r, fh, 1 << 20)
        part.replace(dest)


@dataclass
class TextureAsset:
    id: str
    name: str
    source: str               # polyhaven | ambientcg | custom | procedural
    kind: str                 # texture | hdri
    category: str
    url: str                  # asset page
    author: str
    license: str
    license_url: str
    resolution: str
    path: str                 # folder (or file for HDRIs), relative to the textures root
    maps: dict = field(default_factory=dict)   # map kind -> relative file
    files: list = field(default_factory=list)  # [{path, size, md5}]


def textures_dir() -> Path:
    return paths.ensure_data_dir() / "assets" / "textures"


def curation(repo: Path | None = None) -> dict:
    repo = repo or paths.code_dir()
    return json.loads((repo / "assets" / "textures" / "curation.json").read_text(encoding="utf-8"))


def _md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - integrity check against Poly Haven's published md5, not security
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def confirm_cc0(net: Net, source: str) -> bool:
    """The site-wide license page must state CC0 (checked once per sync per source)."""
    try:
        return "CC0" in net.text(LICENSE_PAGES[source])
    except Exception:  # noqa: BLE001
        return False


def map_kind(filename: str) -> str | None:
    """Map type from a file name by whole tokens (so 'Metal064_Color' is colour, not metalness)."""
    tokens = [x for x in re.split(r"[_\-. ]+", Path(filename).stem.lower()) if x]
    cands = set(tokens) | {a + b for a, b in zip(tokens, tokens[1:])}
    if cands & DX_NORMAL:
        return None  # Blender uses OpenGL normal maps
    for kind in ("normal", "roughness", "height", "ao", "metalness", "emission", "color"):
        if cands & MAP_TOKENS[kind]:
            return kind
    return None


# ------------------------------------------------------------------ Poly Haven
def sync_polyhaven(entry: dict, root: Path, net: Net, res: str, hdri: bool = False) -> TextureAsset:
    aid = entry["id"]
    info = net.json(f"{PH_API}/info/{aid}")
    files = net.json(f"{PH_API}/files/{aid}")
    author = ", ".join(info.get("authors", {}) or {}) or "Poly Haven"
    asset = TextureAsset(aid, info.get("name", aid), "polyhaven", "hdri" if hdri else "texture", entry.get("category", ""),
                         f"https://polyhaven.com/a/{aid}", author, LICENSE, LICENSE_URL, res, "")
    wanted: list[tuple[str, dict]] = []
    if hdri:
        f = (files.get("hdri", {}).get(res) or {}).get("hdr")
        if not f:
            raise RuntimeError(f"{aid}: no {res} .hdr available")
        wanted.append(("hdri", f))
        asset.path = f"polyhaven/hdri/{aid}_{res}.hdr"
    else:
        for api_key, kind in PH_MAPS.items():
            f = (files.get(api_key, {}).get(res) or {})
            f = f.get("jpg") or f.get("png")
            if f:
                wanted.append((kind, f))
        if not any(k == "color" for k, _ in wanted):
            raise RuntimeError(f"{aid}: no colour map at {res}")
        asset.path = f"polyhaven/{aid}_{res}"
    for kind, f in wanted:
        rel = asset.path if hdri else f"{asset.path}/{Path(f['url']).name}"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not (dest.exists() and _md5(dest) == f["md5"]):
            net.download(f["url"], dest)
            if _md5(dest) != f["md5"]:
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"{aid}: checksum mismatch for {Path(f['url']).name}")
        asset.maps[kind] = rel
        asset.files.append({"path": rel, "size": f.get("size"), "md5": f["md5"]})
    return asset


# ------------------------------------------------------------------ ambientCG
def sync_ambientcg(entry: dict, root: Path, net: Net, res: str) -> TextureAsset:
    aid = entry["id"]
    data = net.json(f"{ACG_API}?id={aid}&include=downloadData")
    found = data.get("foundAssets") or []
    if not found:
        raise RuntimeError(f"{aid}: not found on ambientCG")
    a = found[0]
    attr = f"{res.upper()}-JPG"
    downloads = (((a.get("downloadFolders") or {}).get("default") or {}).get("downloadFiletypeCategories") or {}) \
        .get("zip", {}).get("downloads", [])
    dl = next((d for d in downloads if d.get("attribute") == attr), None)
    if dl is None:
        raise RuntimeError(f"{aid}: no {attr} download")
    folder = f"ambientcg/{aid}_{res}"
    asset = TextureAsset(aid, a.get("displayName") or aid, "ambientcg", "texture", entry.get("category", ""),
                         a.get("shortLink") or f"https://ambientcg.com/a/{aid}", "ambientCG (Lennart Demes)",
                         LICENSE, LICENSE_URL, res, folder)
    target = root / folder
    marker = target / ".complete"
    if not marker.exists():
        tmp_zip = root / "ambientcg" / dl["fileName"]
        tmp_zip.parent.mkdir(parents=True, exist_ok=True)
        if not (tmp_zip.exists() and tmp_zip.stat().st_size == dl.get("size")):
            net.download(dl["downloadLink"], tmp_zip)
        if dl.get("size") and tmp_zip.stat().st_size != dl["size"]:
            tmp_zip.unlink(missing_ok=True)
            raise RuntimeError(f"{aid}: size mismatch (download incomplete)")
        with zipfile.ZipFile(tmp_zip) as z:
            if z.testzip() is not None:
                raise RuntimeError(f"{aid}: corrupt zip")
            target.mkdir(parents=True, exist_ok=True)
            for member in z.namelist():
                name = Path(member).name
                if name and Path(name).suffix.lower() in IMAGE_EXT:  # images only, flat (no path traversal)
                    (target / name).write_bytes(z.read(member))
        tmp_zip.unlink(missing_ok=True)
        marker.write_text("ok")
    for f in sorted(target.iterdir()):
        kind = map_kind(f.name) if f.suffix.lower() in IMAGE_EXT else None
        if kind and kind not in asset.maps:
            asset.maps[kind] = f"{folder}/{f.name}"
            asset.files.append({"path": f"{folder}/{f.name}", "size": f.stat().st_size})
    if "color" not in asset.maps:
        raise RuntimeError(f"{aid}: no colour map in the download")
    return asset


# ------------------------------------------------------------------ manifest / credits
def load_manifest(root: Path) -> dict:
    try:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"assets": []}


def write_manifest(root: Path, assets: list[TextureAsset]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    data = {"generated": _dt.datetime.now().isoformat(timespec="seconds"),
            "assets": [asdict(a) for a in sorted(assets, key=lambda a: (a.source, a.id))]}
    (root / "manifest.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    lines = ["# Texture credits", "", "Downloaded by `lyric2resolve assets sync`. All assets are CC0 1.0 "
             "(public domain); credit is not required but appreciated.", ""]
    for a in sorted(assets, key=lambda a: (a.source, a.name.lower())):
        lines.append(f"- **{a.name}** ({a.kind}, {a.resolution}) by {a.author} — {a.source} — {a.url} — {a.license}")
    (root / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped_license: list[str] = field(default_factory=list)


def sync(root: Path | None = None, net: Net | None = None, res: str = "1k", cur: dict | None = None,
         log: Callable[[str], None] = print) -> SyncReport:
    if res not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {RESOLUTIONS}")
    root = root or textures_dir()
    net = net or HttpNet()
    cur = cur if cur is not None else curation()
    existing = {(a["source"], a["id"], a["resolution"]): TextureAsset(**a) for a in load_manifest(root).get("assets", [])}
    assets = dict(existing)
    report = SyncReport()
    jobs = [("polyhaven", e, False) for e in cur.get("polyhaven", [])] + \
           [("polyhaven", e, True) for e in cur.get("polyhaven_hdris", [])] + \
           [("ambientcg", e, False) for e in cur.get("ambientcg", [])]
    cc0 = {s: confirm_cc0(net, s) for s in {j[0] for j in jobs}}
    for i, (source, entry, hdri) in enumerate(jobs, start=1):
        log(f"[{i}/{len(jobs)}] {source} {entry['id']}")
        if not cc0.get(source):
            report.skipped_license.append(f"{source}/{entry['id']}")
            log("  skipped: could not confirm the CC0 license page")
            continue
        try:
            a = sync_polyhaven(entry, root, net, res, hdri) if source == "polyhaven" else \
                sync_ambientcg(entry, root, net, res)
        except Exception as exc:  # noqa: BLE001 - keep going
            report.failed.append(f"{source}/{entry['id']}: {exc}")
            log(f"  FAILED: {exc}")
            continue
        assets[(a.source, a.id, a.resolution)] = a
        report.added.append(f"{source}/{a.id}")
        write_manifest(root, list(assets.values()))   # resumable: progress saved after every asset
    write_manifest(root, list(assets.values()))
    return report


# ------------------------------------------------------------------ browsing (library + custom)
def custom_assets(root: Path) -> list[TextureAsset]:
    """User textures in <textures>/custom: one folder per material, or single images; .hdr/.exr = HDRI."""
    custom = root / "custom"
    out: list[TextureAsset] = []
    if not custom.exists():
        return out
    for item in sorted(custom.iterdir()):
        if item.is_dir():
            maps = {}
            for f in sorted(item.iterdir()):
                k = map_kind(f.name) if f.suffix.lower() in IMAGE_EXT else None
                if k and k not in maps:
                    maps[k] = f"custom/{item.name}/{f.name}"
            if not maps:
                imgs = [f for f in sorted(item.iterdir()) if f.suffix.lower() in IMAGE_EXT]
                if imgs:
                    maps["color"] = f"custom/{item.name}/{imgs[0].name}"
            if maps:
                out.append(TextureAsset(item.name, item.name, "custom", "texture", "custom", "", "you", "your own", "",
                                        "", f"custom/{item.name}", maps))
        elif item.suffix.lower() in IMAGE_EXT:
            kind = "hdri" if item.suffix.lower() in (".hdr", ".exr") else "texture"
            out.append(TextureAsset(item.stem, item.stem, "custom", kind, "custom", "", "you", "your own", "", "",
                                    f"custom/{item.name}", {"hdri" if kind == "hdri" else "color": f"custom/{item.name}"}))
    return out


def list_textures(root: Path | None = None) -> list[dict]:
    root = root or textures_dir()
    lib = [a for a in load_manifest(root).get("assets", [])]
    return lib + [asdict(a) for a in custom_assets(root)]


def main_sync(res: str = "1k") -> int:
    rep = sync(res=res)
    print(f"Textures: {len(rep.added)} ok, {len(rep.failed)} failed, {len(rep.skipped_license)} skipped (license)")
    for f in rep.failed:
        print("  FAILED", f)
    print(f"Folder: {textures_dir()}  (credits in CREDITS.md)")
    return 1 if rep.failed else 0

