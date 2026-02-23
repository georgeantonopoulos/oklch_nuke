"""Initialization helpers for the OKLCH Grade gizmo."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

import nuke

LINEAR_SRGB_ALIASES = (
    "Utility - Linear - sRGB",
    "lin_srgb",
    "Linear sRGB",
    "srgb_linear",
)

# Used only by _add_link_knobs — order determines panel appearance.
_GRADE_LINK_DEFS = (
    ("l_gain",        "L Gain",          "BlinkScript_OKLCHGrade.l_gain"),
    ("l_offset",      "L Offset",        "BlinkScript_OKLCHGrade.l_offset"),
    ("c_gain",        "C Gain",          "BlinkScript_OKLCHGrade.c_gain"),
    ("c_offset",      "C Offset",        "BlinkScript_OKLCHGrade.c_offset"),
    ("hue_shift_deg", "Hue Shift (deg)", "BlinkScript_OKLCHGrade.hue_shift_deg"),
    ("mix",           "Mix",             "BlinkScript_OKLCHGrade.mix"),
    ("clamp_output",  "Clamp Output",    "BlinkScript_OKLCHGrade.clamp_output"),
    ("bypass",        "Bypass",          "BlinkScript_OKLCHGrade.bypass"),
)

# Slider ranges for BlinkScript float params.
# defineParam(name, label, default) has no min/max argument in the Blink API,
# so Nuke assigns a default range (often -1..1 or 0..1) after compilation.
# These must be applied via setRange() after recompile.execute().
_PARAM_RANGES = {
    "l_gain":        (-8.0,   8.0),
    "l_offset":      (-2.0,   2.0),
    "c_gain":        (-8.0,   8.0),
    "c_offset":      (-2.0,   2.0),
    "hue_shift_deg": (-360.0, 360.0),
    "mix":           (0.0,    1.0),
}

_COLORSPACE_LINK_DEFS = (
    ("input_colorspace",  "Input Colorspace",  "OCIOColorSpace_IN.in_colorspace"),
    ("output_colorspace", "Output Colorspace", "OCIOColorSpace_OUT.out_colorspace"),
)


def _knob(node: nuke.Node, name: str):
    return node.knob(name)


def get_ocio_colorspaces() -> List[str]:
    """Return colorspaces from the active OCIO config via nuke.getOcioColorSpaces()."""
    try:
        values = nuke.getOcioColorSpaces()
    except Exception:
        return []
    if not values:
        return []
    seen: set = set()
    result: List[str] = []
    for v in values:
        if v not in seen:
            result.append(v)
            seen.add(v)
    return result


def detect_linear_srgb_space(colorspaces: Iterable[str]) -> Optional[str]:
    """Pick the best linear-sRGB colorspace alias from the active OCIO config."""
    colorspaces = list(colorspaces)
    for alias in LINEAR_SRGB_ALIASES:
        if alias in colorspaces:
            return alias
    lowered = {v.lower(): v for v in colorspaces}
    for alias in LINEAR_SRGB_ALIASES:
        hit = lowered.get(alias.lower())
        if hit:
            return hit
    return None


def _set_text(node: nuke.Node, knob_name: str, value: str) -> None:
    k = _knob(node, knob_name)
    if k is None:
        return
    try:
        k.setValue(value)
    except Exception:
        pass


def _hide_tech_knobs(node: nuke.Node) -> None:
    for name in ("working_linear_srgb_space",):
        k = _knob(node, name)
        if k is None:
            continue
        try:
            k.setFlag(nuke.INVISIBLE)
        except Exception:
            pass


def _find_kernel_path() -> Optional[str]:
    override = os.environ.get("OKLCH_GRADE_KERNEL_PATH", "").strip()
    if override and os.path.isfile(override):
        return override

    here = os.path.abspath(os.path.dirname(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "blink", "oklch_grade_kernel.cpp"))
    if os.path.isfile(candidate):
        return candidate

    for path in nuke.pluginPath():
        candidate_p = os.path.normpath(
            os.path.join(path, "..", "blink", "oklch_grade_kernel.cpp")
        )
        if os.path.isfile(candidate_p):
            return candidate_p

    return None


def _load_kernel_source(group_node: nuke.Node) -> bool:
    """Load the Blink kernel source into the BlinkScript node and recompile.

    Inline (kernelSource) mode only — never set kernelSourceFile.
    Setting kernelSourceFile switches Nuke to file mode and makes it ignore
    the inline source text, silently leaving the kernel uncompiled.

    After recompile.execute() the kernel param knobs (l_gain, hue_shift_deg…)
    exist and are ready for Link_Knob targeting.
    """
    blink = group_node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        _set_text(group_node, "status_text", "Error: BlinkScript node not found.")
        return False

    kernel_path = _find_kernel_path()
    if not kernel_path:
        _set_text(group_node, "status_text", "Error: oklch_grade_kernel.cpp not found.")
        return False

    try:
        with open(kernel_path, "r", encoding="utf-8") as fh:
            source = fh.read()
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error reading kernel: {exc}")
        return False

    # Clear file mode to ensure inline source is used
    ksf = _knob(blink, "kernelSourceFile")
    if ksf is not None:
        ksf.setValue("")

    source_knob = _knob(blink, "kernelSource")
    if source_knob is None:
        _set_text(group_node, "status_text", "Error: kernelSource knob not found.")
        return False

    try:
        source_knob.setValue(source)
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error setting kernel source: {exc}")
        return False

    compile_knob = _knob(blink, "recompile")
    if compile_knob is not None:
        try:
            compile_knob.execute()
        except Exception as exc:
            _set_text(group_node, "status_text", f"Kernel compile error: {exc}")
            return False

    # After recompile, verify the param knobs exist.
    # If they don't, the compile might have failed or is not yet finished.
    if _knob(blink, "l_gain") is None:
        _set_text(group_node, "status_text", "Error: Kernel parameters not found after compile.")
        return False

    # After recompile the param knobs exist but carry Nuke's default range
    # (often -1..1 or 0..1).  Set meaningful ranges so sliders are usable,
    # especially hue_shift_deg which needs -360..360.
    for knob_name, (lo, hi) in _PARAM_RANGES.items():
        k = _knob(blink, knob_name)
        if k is not None:
            try:
                k.setRange(lo, hi)
            except Exception:
                pass

    return True


def _add_link_knobs(group_node: nuke.Node) -> None:
    """Add Link_Knobs that directly reference internal node knobs.

    Must be called after _load_kernel_source so the BlinkScript kernel param
    knobs exist.  Any knob name that already exists on the gizmo is skipped,
    so this is safe to call on script reopen.

    Link_Knob is bidirectional, updates instantly at eval time with no Python
    overhead, and preserves the correct widget type (checkbox stays a checkbox,
    not an expression field).
    """
    all_defs = _COLORSPACE_LINK_DEFS + _GRADE_LINK_DEFS

    # Ensure we are adding knobs to the correct tab. 
    # Adding a Tab_Knob with the same name as an existing one should set the focus.
    group_node.addKnob(nuke.Tab_Knob("OKLCHGrade", "OKLCH Grade"))
    
    for (name, label, target) in all_defs:
        if group_node.knob(name) is not None:
            continue
        try:
            lk = nuke.Link_Knob(name, label)
            lk.setLink(target)
            group_node.addKnob(lk)
        except Exception:
            pass


def _setup_working_space(group_node: nuke.Node) -> None:
    """Detect the linear-sRGB working space and wire the OCIO bridge nodes.

    Sets OCIOColorSpace_IN.out_colorspace and OCIOColorSpace_OUT.in_colorspace
    to the detected alias.  Disables all three internal processing nodes and
    force-sets bypass if no linear-sRGB alias exists in the active OCIO config.
    """
    colorspaces = get_ocio_colorspaces()
    linear_space = detect_linear_srgb_space(colorspaces)

    wk = _knob(group_node, "working_linear_srgb_space")
    if wk is not None:
        try:
            wk.setValue(linear_space or "")
        except Exception:
            pass

    ocio_in  = group_node.node("OCIOColorSpace_IN")
    ocio_out = group_node.node("OCIOColorSpace_OUT")
    blink    = group_node.node("BlinkScript_OKLCHGrade")
    missing  = not bool(linear_space)

    if ocio_in is not None:
        if linear_space and _knob(ocio_in, "out_colorspace") is not None:
            ocio_in["out_colorspace"].setValue(linear_space)
        if _knob(ocio_in, "disable") is not None:
            ocio_in["disable"].setValue(missing)

    if ocio_out is not None:
        if linear_space and _knob(ocio_out, "in_colorspace") is not None:
            ocio_out["in_colorspace"].setValue(linear_space)
        if _knob(ocio_out, "disable") is not None:
            ocio_out["disable"].setValue(missing)

    if blink is not None:
        if _knob(blink, "disable") is not None:
            blink["disable"].setValue(missing)

    if linear_space:
        _set_text(group_node, "status_text", f"Ready. Working space: {linear_space}")
    else:
        _set_text(
            group_node, "status_text",
            "Warning: no linear-sRGB alias found in OCIO config. Bypass enabled.",
        )
        bypass_lk = _knob(group_node, "bypass")
        if bypass_lk is not None:
            try:
                bypass_lk.setValue(True)
            except Exception:
                pass


def initialize_node(node: nuke.Node) -> None:
    """Called from gizmo onCreate: compile kernel, add Link_Knobs, wire OCIO."""
    _hide_tech_knobs(node)
    # compile kernel — BlinkScript param knobs now exist
    if _load_kernel_source(node):
        _add_link_knobs(node)       # add Link_Knobs pointing at all internal knobs
        _setup_working_space(node)  # detect linear-sRGB, enable/disable internal nodes


def handle_knob_changed(node: nuke.Node, changed_knob) -> None:
    """Minimal handler retained for future extensibility.

    All grade and colorspace syncing is handled by Link_Knobs — no Python
    copying needed.  The only guard here is to detect the wrong-node context
    (nuke.thisNode() can return an internal child when the user is inside the
    group) and bail out silently.
    """
    if changed_knob is None:
        return
    if _knob(node, "working_linear_srgb_space") is None:
        return
