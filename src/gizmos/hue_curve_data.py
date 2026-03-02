"""Shared hue-curve data helpers used by both the widget and callbacks modules.

This module has NO Qt or PySide2 dependency and is safe to import in headless
(``nuke -t``) sessions.
"""

from __future__ import annotations

import json
import math
import re
from typing import Iterable, Optional

_DEFAULT_POINTS: tuple[tuple[float, float], ...] = (
    (0.0,    1.0),  # Red      (0°)
    (0.1667, 1.0),  # Yellow  (60°)
    (0.3333, 1.0),  # Green  (120°)
    (0.5,    1.0),  # Cyan   (180°)
    (0.6667, 1.0),  # Blue   (240°)
    (0.8333, 1.0),  # Magenta(300°)
    (1.0,    1.0),  # Red wrap(360°)
)
_HUE_SAMPLE_COUNT = 37
_EPSILON = 1e-6

_SCRIPT_PAIR_RE = re.compile(r"x([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)")
_SAT_CURVE_RE = re.compile(r"sat\s*\{\s*curve\s+([^}]*)\}", re.IGNORECASE)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def normalize_points(
    points: Optional[Iterable[Iterable[float]]],
) -> list[tuple[float, float]]:
    """Sort, deduplicate, clamp, and enforce endpoint wrapping."""
    parsed: list[tuple[float, float]] = []
    if points is not None:
        for pair in points:
            try:
                x_raw, y_raw = pair
                x = clamp(float(x_raw), 0.0, 1.0)
                y = clamp(float(y_raw), 0.0, 2.0)
                parsed.append((x, y))
            except Exception:
                continue

    if not parsed:
        return [(0.0, 1.0), (1.0, 1.0)]

    parsed.sort(key=lambda item: item[0])

    deduped: list[tuple[float, float]] = []
    for x, y in parsed:
        if not deduped or abs(deduped[-1][0] - x) > _EPSILON:
            deduped.append((x, y))
        else:
            deduped[-1] = (x, y)

    if deduped[0][0] > _EPSILON:
        deduped.insert(0, (0.0, deduped[0][1]))
    else:
        deduped[0] = (0.0, deduped[0][1])

    if deduped[-1][0] < (1.0 - _EPSILON):
        deduped.append((1.0, deduped[-1][1]))
    else:
        deduped[-1] = (1.0, deduped[-1][1])

    y_wrap = deduped[0][1]
    deduped[0] = (0.0, y_wrap)
    deduped[-1] = (1.0, y_wrap)

    if len(deduped) < 2:
        return [(0.0, 1.0), (1.0, 1.0)]

    return deduped


def _catmull_rom_y_normalized(pts: list[tuple[float, float]], x: float) -> float:
    """Evaluate Catmull-Rom spline Y at *x* through pre-normalized *pts*."""
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]

    seg = 0
    for idx in range(len(pts) - 1):
        if pts[idx][0] <= x <= pts[idx + 1][0]:
            seg = idx
            break

    p1 = pts[seg]
    p2 = pts[seg + 1]

    if abs(p2[0] - p1[0]) < _EPSILON:
        return p1[1]

    if seg > 0:
        p0 = pts[seg - 1]
    else:
        p0 = (2.0 * p1[0] - p2[0], 2.0 * p1[1] - p2[1])

    if seg + 2 < len(pts):
        p3 = pts[seg + 2]
    else:
        p3 = (2.0 * p2[0] - p1[0], 2.0 * p2[1] - p1[1])

    t = (x - p1[0]) / (p2[0] - p1[0])
    t2 = t * t
    t3 = t2 * t

    y = 0.5 * (
        (2.0 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
    )
    return y


def catmull_rom_y(points: list[tuple[float, float]], x: float) -> float:
    """Evaluate Catmull-Rom spline Y at *x* through *points*.

    Points are normalized defensively.  Use ``_catmull_rom_y_normalized``
    when the caller has already validated the points list.
    """
    return _catmull_rom_y_normalized(normalize_points(points), x)


def points_to_json(points: list[tuple[float, float]]) -> str:
    """Serialize control points to compact JSON for the hidden String_Knob."""
    payload = [[round(x, 6), round(y, 6)] for x, y in normalize_points(points)]
    return json.dumps(payload, separators=(",", ":"))


def points_to_hue_script(points: list[tuple[float, float]]) -> str:
    """Build the HueCorrect sat-curve TCL ``fromScript()`` string."""
    pts = normalize_points(points)
    tokens: list[str] = []
    for index in range(_HUE_SAMPLE_COUNT):
        x = index / float(_HUE_SAMPLE_COUNT - 1)
        y = clamp(catmull_rom_y(pts, x), 0.0, 2.0)
        tokens.append(f"x{x:.6f} {y:.6f}")
    curve_data = " ".join(tokens)
    # HueCorrect's knob ``fromScript`` expects raw key/value list words
    # (sat/lum/red/...) rather than one extra outer-braced word.
    return (
        "sat {curve " + curve_data + "}"
        " lum {} red {} green {} blue {}"
        " r_sup {} g_sup {} b_sup {} sat_thrsh {}"
    )


def points_to_lut_samples(
    points: list[tuple[float, float]],
    sample_count: int = _HUE_SAMPLE_COUNT,
) -> list[tuple[float, float]]:
    """Sample normalized control points into evenly spaced LUT values."""
    pts = normalize_points(points)
    count = max(int(sample_count), 2)
    out: list[tuple[float, float]] = []
    for index in range(count):
        x = index / float(count - 1)
        y = clamp(_catmull_rom_y_normalized(pts, x), 0.0, 2.0)
        out.append((x, y))
    return out


def samples_to_expression(samples: list[tuple[float, float]], x_var: str = "lutx") -> str:
    """Convert sampled LUT points to nested ternary Expression-node syntax."""
    if not samples:
        return "1.0"
    if len(samples) == 1:
        return f"{samples[0][1]:.6f}"

    pieces: list[str] = []
    for idx in range(len(samples) - 1):
        x0, y0 = samples[idx]
        x1, y1 = samples[idx + 1]
        dx = max(x1 - x0, _EPSILON)
        slope = (y1 - y0) / dx
        seg_expr = f"({y0:.6f} + ({x_var} - {x0:.6f}) * {slope:.6f})"
        pieces.append(f"{x_var} < {x1:.6f} ? {seg_expr} : ")

    return "".join(pieces) + f"{samples[-1][1]:.6f}"


def points_to_lut_expression(
    points: list[tuple[float, float]],
    *,
    x_var: str = "lutx",
    sample_count: int = _HUE_SAMPLE_COUNT,
) -> str:
    """Build Expression-node formula for a direct grayscale hue LUT."""
    samples = points_to_lut_samples(points, sample_count=sample_count)
    core = samples_to_expression(samples, x_var=x_var)
    return (
        f"{x_var} <= 0.0 ? {samples[0][1]:.6f} : "
        f"({x_var} >= 1.0 ? {samples[-1][1]:.6f} : ({core}))"
    )


def parse_hue_script_points(script: str) -> Optional[list[tuple[float, float]]]:
    """Extract control points from a HueCorrect sat-curve TCL script.

    Returns ``None`` when the script does not contain at least 2 key pairs.
    """
    text = str(script or "")
    sat_match = _SAT_CURVE_RE.search(text)
    scan_text = sat_match.group(1) if sat_match else text
    pairs = _SCRIPT_PAIR_RE.findall(scan_text)
    if len(pairs) < 2:
        return None
    parsed = [(float(x_raw), float(y_raw)) for x_raw, y_raw in pairs]
    return normalize_points(parsed)


# ---------------------------------------------------------------------------
# Linear-sRGB -> OKLCH conversion (mirrors oklch_grade_kernel.cpp exactly)
# ---------------------------------------------------------------------------

_CHROMA_FLOOR = 4e-6  # matches kernel: c <= 0.000004f


def _signed_cbrt(x: float) -> float:
    """Cube root preserving sign — mirrors kernel ``signed_cbrt()``."""
    if x == 0.0:
        return 0.0
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def linsrgb_to_oklch(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert linear-sRGB to OKLCH ``(L, C, H)``.

    Uses the exact CSS Color 4 / Bjorn Ottosson matrices from
    ``oklch_grade_kernel.cpp``.  *H* is in degrees ``[0, 360)``.
    """
    # linear_srgb_to_xyz
    x = 0.4123907992659595 * r + 0.3575843393838780 * g + 0.1804807884018343 * b
    y = 0.2126390058715104 * r + 0.7151686787677559 * g + 0.0721923153607337 * b
    z = 0.0193308187155918 * r + 0.1191947797946260 * g + 0.9505321522496606 * b

    # xyz_to_oklab
    l = 0.8190224379967030 * x + 0.3619062600528904 * y + -0.1288737815209879 * z
    m = 0.0329836539323885 * x + 0.9292868615863434 * y + 0.0361446663506424 * z
    s = 0.0481771893596242 * x + 0.2642395317527308 * y + 0.6335478284694309 * z

    l_ = _signed_cbrt(l)
    m_ = _signed_cbrt(m)
    s_ = _signed_cbrt(s)

    L = 0.2104542683093140 * l_ + 0.7936177747023054 * m_ + -0.0040720430116193 * s_
    a = 1.9779985324311684 * l_ + -2.4285922420485799 * m_ + 0.4505937096174110 * s_
    b_val = 0.0259040424655478 * l_ + 0.7827717124575296 * m_ + -0.8086757549230774 * s_

    # oklab_to_oklch
    C = math.sqrt(a * a + b_val * b_val)
    H = math.atan2(b_val, a) * 57.2957795131  # rad -> deg
    if H < 0.0:
        H += 360.0
    if C <= _CHROMA_FLOOR:
        H = 0.0

    return (L, C, H)


def linsrgb_to_hue_normalized(r: float, g: float, b: float) -> tuple[float, float]:
    """Return ``(hue_x, chroma)`` from linear-sRGB.

    *hue_x* is in ``[0.0, 1.0]``, suitable for the curve widget X axis.
    """
    _L, C, H = linsrgb_to_oklch(r, g, b)
    return (H / 360.0, C)
