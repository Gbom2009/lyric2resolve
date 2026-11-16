"""Font library: sync curated Google Fonts (OFL / Apache-2.0 only), manifest + credits,
per-user install on Windows so DaVinci Resolve can use them.

Sources (checked 2026-11-16):
- license + metadata: https://raw.githubusercontent.com/google/fonts/main/<ofl|apache>/<dir>/METADATA.pb
- static TTF files:   https://fonts.googleapis.com/css2?family=<Name>:wght@400;700  (a plain User-Agent
  gets TrueType URLs on fonts.gstatic.com; static instances work better in Resolve than variable fonts)
Downloads happen on the user's PC (`lyric2resolve assets sync --fonts`), never in CI.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from lyric2resolve import paths

ALLOWED_LICENSES = {"OFL": "SIL Open Font License 1.1", "APACHE2": "Apache License 2.0"}
LICENSE_URLS = {"OFL": "https://openfontlicense.org", "APACHE2": "https://www.apache.org/licenses/LICENSE-2.0"}
META_URL = "https://raw.githubusercontent.com/google/fonts/main/{dir}/METADATA.pb"
CSS_URL = "https://fonts.googleapis.com/css2?family={family}:wght@{weights}"
CSS_URL_PLAIN = "https://fonts.googleapis.com/css2?family={family}"
USER_AGENT = "Mozilla/4.0 (lyric2resolve font sync)"   # old UA -> TrueType URLs
FONT_EXT = (".ttf", ".otf")
# System fonts present on every Windows PC (not redistributed, just suggested in the picker)
SYSTEM_FALLBACK = ["Arial", "Arial Black", "Impact", "Segoe UI", "Segoe UI Black", "Bahnschrift", "Verdana",
                   "Tahoma", "Trebuchet MS", "Georgia"]

Fetch = Callable[[str], bytes]


def http_fetch(url: str, timeout: float = 30, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 - network errors of all kinds
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}: {last}")


# ------------------------------------------------------------------ parsing
def parse_metadata(text: str) -> dict:
    """Minimal parser for Google Fonts METADATA.pb (protobuf text format; top-level fields we need)."""
    out: dict = {"fonts": []}
    depth = 0
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.endswith("{"):
            depth += 1
            if depth == 1 and line.startswith("fonts"):
                current = {}
            continue
        if line == "}":
            depth -= 1
            if depth == 0 and current is not None:
                out["fonts"].append(current)
                current = None
            continue
        m = re.match(r'^(\w+):\s*"?(.*?)"?$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if depth == 0 and key in ("name", "designer", "license", "category"):
            out[key] = val
        elif depth == 1 and current is not None:
            current[key] = val
    return out


def parse_css(css: str) -> list[dict]:
    """@font-face blocks -> [{style, weight, url}] (TrueType/OpenType only)."""
    faces = []
    for block in re.findall(r"@font-face\s*{(.*?)}", css, re.S):
        style = re.search(r"font-style:\s*(\w+)", block)
        weight = re.search(r"font-weight:\s*(\d+)", block)
        url = re.search(r"url\((https://[^)]+\.(?:ttf|otf))\)", block)
        if url:
            faces.append({"style": style.group(1) if style else "normal",
                          "weight": int(weight.group(1)) if weight else 400, "url": url.group(1)})
    return faces


WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                700: "Bold", 800: "ExtraBold", 900: "Black"}


def file_name(family: str, weight: int, style: str, ext: str = ".ttf") -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", family)
    w = WEIGHT_NAMES.get(weight, str(weight))
    return f"{base}-{w}{'Italic' if style == 'italic' else ''}{ext}"


# ------------------------------------------------------------------ manifest
@dataclass
class FontFile:
    path: str            # relative to the fonts folder
    weight: int
    style: str
    sha256: str
    url: str = ""


@dataclass
class FontFamily:
    family: str
    license: str
    license_name: str
    license_url: str
    designer: str
    source: str
    category: str = ""
    files: list[FontFile] = field(default_factory=list)


def fonts_dir() -> Path:
    return paths.ensure_data_dir() / "assets" / "fonts"


def load_manifest(root: Path) -> dict:
    try:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"families": []}


def write_manifest(root: Path, families: list[FontFamily]) -> Path:
    data = {"generated": _dt.datetime.now().isoformat(timespec="seconds"),
            "families": [asdict(f) for f in sorted(families, key=lambda f: f.family.lower())]}
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    write_credits(root, families)
    return root / "manifest.json"


def write_credits(root: Path, families: list[FontFamily]) -> Path:
    lines = ["# Font credits", "", "Fonts downloaded by `lyric2resolve assets sync --fonts` from Google Fonts.",
             "Each family's license was verified from its METADATA.pb before downloading.", ""]
    for f in sorted(families, key=lambda f: f.family.lower()):
        lines.append(f"- **{f.family}** by {f.designer or 'unknown'} — {f.license_name} ({f.license_url}) — "
                     f"source: {f.source}")
    path = root / "CREDITS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def curation(repo: Path | None = None) -> list[dict]:
    repo = repo or paths.code_dir()
    return json.loads((repo / "assets" / "fonts" / "curation.json").read_text(encoding="utf-8"))["families"]


# ------------------------------------------------------------------ sync
@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)   # license not allowed
    failed: list[str] = field(default_factory=list)


def sync_family(entry: dict, root: Path, fetch: Fetch, existing: dict | None = None) -> FontFamily:
    """Verify license from METADATA.pb, then download static TTFs. Raises PermissionError when the
    license is not OFL/APACHE2."""
    meta = parse_metadata(fetch(META_URL.format(dir=entry["repo_dir"])).decode("utf-8", "replace"))
    lic = meta.get("license", "").upper()
    if lic not in ALLOWED_LICENSES:
        raise PermissionError(f"{entry['family']}: license {lic or 'unknown'} is not OFL/Apache-2.0")
    family = meta.get("name") or entry["family"]
    weights = ";".join(str(w) for w in sorted(entry.get("weights") or [400, 700]))
    q = urllib.parse.quote(family).replace("%20", "+")
    try:
        css = fetch(CSS_URL.format(family=q, weights=weights)).decode("utf-8", "replace")
        faces = parse_css(css)
    except RuntimeError:
        faces = []
    if not faces:  # family without those weights (e.g. single-weight display fonts)
        faces = parse_css(fetch(CSS_URL_PLAIN.format(family=q)).decode("utf-8", "replace"))
    if not faces:
        raise RuntimeError(f"{family}: no TrueType files offered")
    fam = FontFamily(family, lic, ALLOWED_LICENSES[lic], LICENSE_URLS[lic], meta.get("designer", ""),
                     f"https://fonts.google.com/specimen/{q}", entry.get("category", ""))
    have = {f["path"]: f for f in (existing or {}).get("files", [])}
    for face in faces:
        rel = f"{re.sub(r'[^A-Za-z0-9]+', '', family)}/{file_name(family, face['weight'], face['style'])}"
        target = root / rel
        if rel in have and target.exists() and _sha(target) == have[rel]["sha256"]:
            fam.files.append(FontFile(**have[rel]))
            continue
        data = fetch(face["url"])
        if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise RuntimeError(f"{family}: downloaded file is not a font ({face['url']})")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(target)
        fam.files.append(FontFile(rel, face["weight"], face["style"], hashlib.sha256(data).hexdigest(), face["url"]))
    return fam


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(root: Path | None = None, fetch: Fetch = http_fetch, families: list[dict] | None = None,
         log: Callable[[str], None] = print, delay_s: float = 0.3) -> SyncReport:
    root = root or fonts_dir()
    families = families if families is not None else curation()
    manifest = {f["family"]: f for f in load_manifest(root).get("families", [])}
    result: dict[str, FontFamily] = {}
    for name, f in manifest.items():  # keep what is already there
        f2 = dict(f)
        f2["files"] = [FontFile(**x) for x in f.get("files", [])]
        result[name] = FontFamily(**f2)
    report = SyncReport()
    for i, entry in enumerate(families):
        name = entry["family"]
        log(f"[{i + 1}/{len(families)}] {name}")
        try:
            fam = sync_family(entry, root, fetch, manifest.get(name))
        except PermissionError as exc:
            report.rejected.append(str(exc))
            log(f"  skipped: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - keep going, report at the end
            report.failed.append(f"{name}: {exc}")
            log(f"  FAILED: {exc}")
            continue
        (report.skipped if name in manifest and fam.files == result.get(name, fam).files else report.added).append(name)
        result[fam.family] = fam
        write_manifest(root, list(result.values()))  # resumable: manifest updated after every family
        time.sleep(delay_s)  # be polite to the servers
    write_manifest(root, list(result.values()))
    return report


# ------------------------------------------------------------------ listing (editor picker)
def list_fonts(root: Path | None = None) -> list[dict]:
    """Families for the picker: downloaded (with license), user custom, Windows system fallbacks."""
    root = root or fonts_dir()
    out = []
    for f in load_manifest(root).get("families", []):
        out.append({"family": f["family"], "source": "library", "license": f["license"], "category": f.get("category", ""),
                    "files": [x["path"] for x in f.get("files", [])]})
    custom = root / "custom"
    if custom.exists():
        for p in sorted(custom.rglob("*")):
            if p.suffix.lower() in FONT_EXT:
                out.append({"family": p.stem.split("-")[0], "source": "custom", "license": "your own",
                            "category": "", "files": [str(p.relative_to(root)).replace("\\", "/")]})
    seen = {f["family"].lower() for f in out}
    out += [{"family": n, "source": "system", "license": "Windows", "category": "", "files": []}
            for n in SYSTEM_FALLBACK if n.lower() not in seen]
    return out


# ------------------------------------------------------------------ per-user install (Windows + Mac)
def user_fonts_dir(env: dict | None = None, platform: str | None = None) -> Path:
    """Fonts folder of the current user: Windows %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts, Mac ~/Library/Fonts."""
    import os

    env = os.environ if env is None else env
    if (platform or sys.platform) == "darwin":
        return Path.home() / "Library" / "Fonts"
    return Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Microsoft" / "Windows" / "Fonts"


class Registry:
    """HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts (per-user fonts, Windows 10 1809+)."""

    KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"

    def set(self, name: str, value: str) -> None:  # pragma: no cover - Windows only
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def install_fonts(root: Path | None = None, target: Path | None = None, registry=None,
                  notify: Callable[[], None] | None = None) -> list[str]:
    """Copy library + custom fonts to the current user's fonts folder (Windows: also registered; Mac: macOS picks
    up ~/Library/Fonts by itself).

    Returns the installed file names. Resolve must be restarted to see new fonts.
    """
    import shutil

    root = root or fonts_dir()
    target = target or user_fonts_dir()
    if registry is None:
        if sys.platform.startswith("win"):
            registry = Registry()
        elif sys.platform != "darwin":
            raise RuntimeError("Installing fonts is only supported on Windows and macOS")
    target.mkdir(parents=True, exist_ok=True)
    installed = []
    files = [root / x["path"] for f in load_manifest(root).get("families", []) for x in f.get("files", [])]
    custom = root / "custom"
    if custom.exists():
        files += [p for p in custom.rglob("*") if p.suffix.lower() in FONT_EXT]
    for src in files:
        if not src.exists():
            continue
        dst = target / src.name
        if not dst.exists() or _sha(dst) != _sha(src):
            shutil.copy2(src, dst)
        if registry is not None:
            kind = "OpenType" if src.suffix.lower() == ".otf" else "TrueType"
            registry.set(f"{src.stem} ({kind})", str(dst))
        installed.append(src.name)
    if notify:
        notify()
    elif sys.platform.startswith("win"):  # pragma: no cover - tell running apps fonts changed
        try:
            import ctypes

            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)
        except Exception:  # noqa: BLE001
            pass
    return installed
