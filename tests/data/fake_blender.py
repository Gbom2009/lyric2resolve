"""A fake 'blender' for tests: prints Blender-like output and writes real PNG frames.

Env: FAKE_GPU (json for the GPU probe), FAKE_FAIL_AT (frame number -> exit 1), FAKE_SLEEP (s per frame).
"""
import json
import os
import struct
import sys
import time
import zlib
from pathlib import Path


def png(path, value):
    raw = b"".join(b"\x00" + bytes([value]) * 8 for _ in range(8))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


args = sys.argv[1:]
if args == ["--version"]:
    print("Blender 5.3.0\n\tbuild date: fake")
    sys.exit(0)
after = args[args.index("--") + 1:] if "--" in args else []
script = args[args.index("-P") + 1] if "-P" in args else ""
if script.endswith("l2r_gpu_probe.py"):
    print("L2R_GPU" + os.environ.get("FAKE_GPU", '{"backends": {}}'))
    sys.exit(0)
if "-a" not in args:  # build the scene
    data_path = Path(after[0])
    data = json.loads(data_path.read_text())
    for a in data["aspects"]:
        (data_path.parent / f"{data['name']}_{a.replace(':', 'x')}.blend").write_bytes(b"BLENDER-fake")
        print(f"l2r: saved {a}")
    sys.exit(0)
job = json.loads(Path(after[0]).read_text())
s, e = int(args[args.index("-s") + 1]), int(args[args.index("-e") + 1])
prefix = Path(job["output"])
prefix.parent.mkdir(parents=True, exist_ok=True)
print("L2R_SETUP ok", job["engine"], job["width"], job["height"])
fail = int(os.environ.get("FAKE_FAIL_AT", "0"))
for f in range(s, e + 1):
    out = prefix.parent / f"{prefix.name}{f:04d}.png"
    if out.exists():
        continue
    if f == fail:
        print(f"Error: fake crash at frame {f}")
        sys.exit(1)
    print(f"Fra:{f} Mem:12.00M (Peak 20M) | Time:00:00.10 | Rendering 1 / 1 samples", flush=True)
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    png(out, (f * 7) % 255)
    print(f"Saved: '{out}'", flush=True)
    print(" Time: 00:00.12 (Saving: 00:00.01)", flush=True)
