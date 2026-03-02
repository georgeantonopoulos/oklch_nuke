"""Shared hue-curve data helpers used by both the widget and callbacks modules.

This module has NO Qt or PySide2 dependency and is safe to import in headless
(``nuke -t``) sessions.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

_DEFAULT_POINTS: tuple[tuple[float, float], ...] = ((0.0, 1.0), (1.0, 1.0))
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


def catmull_rom_y(points: list[tuple[float, float]], x: float) -> float:
    """Evaluate Catmull-Rom spline Y at *x* through *points*."""
    pts = normalize_points(points)
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
    return (
        "{sat {curve " + curve_data + "}"
        " lum {} red {} green {} blue {}"
        " r_sup {} g_sup {} b_sup {} sat_thrsh {}}"
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
