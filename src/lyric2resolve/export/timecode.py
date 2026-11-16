"""Frame-accurate time math: fps as exact rationals, timecode <-> frames, FCPXML rational times.

NTSC rates (23.976, 29.97, 59.94) use 1000/1001 rates with NON-drop-frame timecode (NDF),
which is what DaVinci Resolve uses by default for new timelines at those rates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

_NTSC = {23.976: (24000, 1001), 29.97: (30000, 1001), 47.952: (48000, 1001), 59.94: (60000, 1001)}


@dataclass(frozen=True)
class Rate:
    num: int    # frames = num / den per second
    den: int

    @classmethod
    def of(cls, fps: float) -> "Rate":
        for k, (n, d) in _NTSC.items():
            if abs(fps - k) < 0.01:
                return cls(n, d)
        if abs(fps - round(fps)) < 1e-6 and fps > 0:
            return cls(int(round(fps)), 1)
        raise ValueError(f"unsupported frame rate {fps}")

    @property
    def fps(self) -> Fraction:
        return Fraction(self.num, self.den)

    @property
    def timebase(self) -> int:
        """Frames per timecode second (24 for 23.976, 30 for 29.97)."""
        return math.ceil(self.num / self.den)

    @property
    def ntsc(self) -> bool:
        return self.den == 1001

    @property
    def frame_duration(self) -> str:
        return fcp_time(1, self)

    def frames(self, seconds: float) -> int:
        """Nearest frame for a time in seconds."""
        return int(round(Fraction(seconds).limit_denominator(1_000_000) * self.fps))

    def seconds(self, frames: int) -> float:
        return float(Fraction(frames) / self.fps)


def fcp_time(frames: int, rate: Rate) -> str:
    """FCPXML rational time string for a frame count, e.g. 1001/24000s or 5s."""
    t = Fraction(frames * rate.den, rate.num)
    if t.denominator == 1:
        return f"{t.numerator}s"
    return f"{t.numerator}/{t.denominator}s"


def parse_fcp_time(value: str) -> Fraction:
    m = re.fullmatch(r"(-?\d+)(?:/(\d+))?s", value.strip())
    if not m:
        raise ValueError(f"bad FCPXML time {value!r}")
    return Fraction(int(m.group(1)), int(m.group(2) or 1))


_TC = re.compile(r"^(\d{1,2})[:;](\d{2})[:;](\d{2})[:;.](\d{2,3})$")


def tc_to_frames(tc: str, rate: Rate) -> int:
    """NDF timecode -> frame count (timebase = rounded fps)."""
    m = _TC.match(tc.strip())
    if not m:
        raise ValueError(f"bad timecode {tc!r}; use HH:MM:SS:FF")
    h, mi, s, f = (int(x) for x in m.groups())
    tb = rate.timebase
    if mi > 59 or s > 59 or f >= tb:
        raise ValueError(f"timecode {tc} out of range for {tb} fps")
    return ((h * 60 + mi) * 60 + s) * tb + f


def frames_to_tc(frames: int, rate: Rate) -> str:
    tb = rate.timebase
    f = frames % tb
    s = frames // tb
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"
