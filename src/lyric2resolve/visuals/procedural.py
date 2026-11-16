"""Procedural tileable textures generated on demand (numpy only; PNG written with zlib).

Patterns: noise (fractal value noise), grid (neon lines), hex (honeycomb edges), cracks (voronoi edges, good
emission masks for lava/energy looks), stripes. All tile seamlessly. Saved to
<textures>/procedural/<name>.png so the library and the Blender material builder can use them.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

PATTERNS = ("noise", "grid", "hex", "cracks", "stripes")


def write_png(path: Path, img: np.ndarray) -> Path:
    """8-bit grayscale (H,W) or RGB (H,W,3) PNG, no external dependencies."""
    a = np.clip(img, 0, 1)
    a = (a * 255 + 0.5).astype(np.uint8)
    h, w = a.shape[:2]
    ctype = 0 if a.ndim == 2 else 2
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def _tile_noise(size: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    g = rng.random((cells, cells))
    xs = np.arange(size) * cells / size
    i0 = np.floor(xs).astype(int)
    f = xs - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells  # wrap -> seamless
    a = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
    b = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def noise(size=512, seed=0, octaves=5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out, amp, total = np.zeros((size, size)), 1.0, 0.0
    for o in range(octaves):
        out += amp * _tile_noise(size, 4 * 2 ** o, rng)
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / (np.ptp(out) or 1)


def grid(size=512, cells=8, width=0.04, glow=0.12) -> np.ndarray:
    u = (np.arange(size) / size * cells) % 1.0
    d = np.minimum(u, 1 - u)
    line = np.exp(-((d / width) ** 2)) + 0.35 * np.exp(-((d / glow) ** 2))
    return np.clip(np.maximum(line[None, :], line[:, None]), 0, 1)


def _toroidal_points(n, rng):
    return rng.random((n, 2))


def cracks(size=512, cells=24, seed=0, sharp=40.0) -> np.ndarray:
    """F2-F1 voronoi distance (edges light up), seamless via toroidal distance."""
    rng = np.random.default_rng(seed)
    pts = _toroidal_points(cells, rng)
    yy, xx = np.mgrid[0:size, 0:size] / size
    d = []
    for px, py in pts:
        dx = np.abs(xx - px)
        dy = np.abs(yy - py)
        dx = np.minimum(dx, 1 - dx)
        dy = np.minimum(dy, 1 - dy)
        d.append(np.sqrt(dx * dx + dy * dy))
    d = np.sort(np.stack(d), axis=0)
    edge = d[1] - d[0]
    return np.exp(-edge * sharp)


def hex_grid(size=512, cells=8, width=0.06) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size] / size * cells
    xx = xx * 2 / np.sqrt(3)
    q = xx
    r = yy - xx / 2
    # cube coords distance to nearest hex centre
    rx, ry = np.round(q), np.round(r)
    fx, fy = q - rx, r - ry
    fz = -fx - fy
    dist = np.maximum(np.abs(fx), np.maximum(np.abs(fy), np.abs(fz)))
    return np.clip(1 - np.abs(dist - 0.5) / width, 0, 1)


def stripes(size=512, count=16, width=0.25) -> np.ndarray:
    u = (np.arange(size) / size * count) % 1.0
    return np.tile((u < width).astype(float), (size, 1))


GENERATORS = {"noise": noise, "grid": grid, "hex": hex_grid, "cracks": cracks, "stripes": stripes}


def generate(pattern: str, out_dir: Path, size: int = 512, **kw) -> Path:
    if pattern not in GENERATORS:
        raise ValueError(f"unknown pattern {pattern!r}; use one of {PATTERNS}")
    img = GENERATORS[pattern](size=size, **kw)
    return write_png(Path(out_dir) / f"{pattern}_{size}.png", img)
