"""Initialization helpers for the OKLCH Grade gizmo."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

import nuke

LINEAR_SRGB_ALIASES = (
    "Utility - Linear - sRGB",  # Prioritize ACES alias
    "lin_srgb",
    "Linear sRGB",
    "srgb_linear",
)

# Used only by _add_link_knobs — order determines panel appearance.
# Tuples: (knob_name, label, link_target).
# A tuple with a None link_target signals a UI divider (Text_Knob separator).
_GRADE_LINK_DEFS = (
    # --- Lightness & Chroma ---
    ("l_gain",                  "L Gain",               "BlinkScript_OKLCHGrade.OKLCHGrade_L Gain"),
    ("l_offset",                "L Offset",             "BlinkScript_OKLCHGrade.OKLCHGrade_L Offset"),
    ("c_gain",                  "C Gain",               "BlinkScript_OKLCHGrade.OKLCHGrade_C Gain"),
    ("c_offset",                "C Offset",             "BlinkScript_OKLCHGrade.OKLCHGrade_C Offset"),
    # --- Global Hue ---
    ("hue_shift_deg",           "Hue Shift (deg)",      "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift (deg)"),
    ("hue_chroma_threshold",    "Hue Chroma Threshold", "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Chroma Threshold"),
    # --- Hue Band Selectors (divider inserted in _add_link_knobs) ---
    ("hue_shift_red",           "Hue Shift Red",        "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Red"),
    ("hue_shift_yellow",        "Hue Shift Yellow",     "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Yellow"),
    ("hue_shift_green",         "Hue Shift Green",      "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Green"),
    ("hue_shift_cyan",          "Hue Shift Cyan",       "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Cyan"),
    ("hue_shift_blue",          "Hue Shift Blue",       "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Blue"),
    ("hue_shift_magenta",       "Hue Shift Magenta",    "BlinkScript_OKLCHGrade.OKLCHGrade_Hue Shift Magenta"),
    # --- Utilities ---
    ("mix",                     "Mix",                  "BlinkScript_OKLCHGrade.OKLCHGrade_Mix"),
    ("clamp_output",            "Clamp Output",         "BlinkScript_OKLCHGrade.OKLCHGrade_Clamp Output"),
    ("bypass",                  "Bypass",               "BlinkScript_OKLCHGrade.OKLCHGrade_Bypass"),
    ("debug_mode",              "Debug Mode",           "BlinkScript_OKLCHGrade.OKLCHGrade_Debug Mode"),
)

# Slider ranges for BlinkScript float params.
# defineParam(name, label, default) has no min/max argument in the Blink API,
# so Nuke assigns a default range (often -1..1 or 0..1) after compilation.
# These must be applied via setRange() after recompile.execute().
_PARAM_RANGES = {
    # Lightness
    "OKLCHGrade_L Gain":               (0.0,    3.0),
    "OKLCHGrade_L Offset":             (-1.0,   1.0),
    # Chroma
    "OKLCHGrade_C Gain":               (0.0,    2.0),
    "OKLCHGrade_C Offset":             (-0.5,   0.5),
    # Global hue
    "OKLCHGrade_Hue Shift (deg)":      (-180.0, 180.0),
    # Chroma threshold: 0 = shift everything, 0.2 = aggressive grey protection.
    # OKLCH chroma for sRGB colours typically spans 0..~0.37; a threshold of
    # 0.05 protects near-neutral values while leaving saturated colours free.
    "OKLCHGrade_Hue Chroma Threshold": (0.0,    0.2),
    # Hue band selectors — same degree range as global shift
    "OKLCHGrade_Hue Shift Red":        (-90.0,  90.0),
    "OKLCHGrade_Hue Shift Yellow":     (-90.0,  90.0),
    "OKLCHGrade_Hue Shift Green":      (-90.0,  90.0),
    "OKLCHGrade_Hue Shift Cyan":       (-90.0,  90.0),
    "OKLCHGrade_Hue Shift Blue":       (-90.0,  90.0),
    "OKLCHGrade_Hue Shift Magenta":    (-90.0,  90.0),
    # Utilities
    "OKLCHGrade_Mix":                  (0.0,    1.0),
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
    
    # 1. Exact alias match (prioritized list)
    for alias in LINEAR_SRGB_ALIASES:
        if alias in colorspaces:
            return alias
            
    # 2. Case-insensitive alias match
    lowered = {v.lower(): v for v in colorspaces}
    for alias in LINEAR_SRGB_ALIASES:
        hit = lowered.get(alias.lower())
        if hit:
            return hit
            
    # 3. Aggressive search for 'linear' AND 'srgb'
    for v in colorspaces:
        v_low = v.lower()
        if "linear" in v_low and "srgb" in v_low:
            return v
            
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

    ksf = _knob(blink, "kernelSourceFile")
    if ksf is None:
        _set_text(group_node, "status_text", "Error: kernelSourceFile knob not found.")
        return False

    try:
        ksf.setValue(kernel_path)
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error setting path: {exc}")
        return False

    # Execute the Load button to read the file into the node
    load_button = _knob(blink, "reloadKernelSourceFile")
    if load_button:
        load_button.execute()

    # Recompile is synchronous — knobs exist immediately after
    compile_button = _knob(blink, "recompile")
    if compile_button:
        compile_button.execute()

    # Check if compilation succeeded by looking for the first param knob
    if _knob(blink, "OKLCHGrade_L Gain") is None:
        available = sorted(k for k in blink.knobs().keys() if not k.startswith("__"))
        _set_text(
            group_node, "status_text",
            f"Error: Kernel params missing after compile. Present: {available}"
        )
        return False

    # Set meaningful UI ranges on the param knobs
    for knob_name, (lo, hi) in _PARAM_RANGES.items():
        k = _knob(blink, knob_name)
        if k:
            k.setRange(lo, hi)

    return True


# Hue anchor tooltips: explain what each band label means in perceptual OKLCH terms.
# Shown as a Text_Knob separator inserted before the band sliders.
_HUE_BAND_TOOLTIP = (
    "Hue Band Selectors — each slider shifts only pixels in that colour range.\n"
    "Bands use a 60° cosine window so neighbours blend smoothly.\n"
    "Shifts fade to zero for achromatic pixels (see Hue Chroma Threshold).\n"
    "\n"
    "Approximate OKLCH hue anchors:\n"
    "  Red      ~   0° / 360°\n"
    "  Yellow   ~  85°\n"
    "  Green    ~ 145°\n"
    "  Cyan     ~ 195°\n"
    "  Blue     ~ 265°\n"
    "  Magenta  ~ 325°"
)

# Knob names that mark the start of the hue-band section (divider goes before them).
_HUE_BAND_FIRST = "hue_shift_red"


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
    # Adding a Tab_Knob with the same name as an existing one sets the focus.
    group_node.addKnob(nuke.Tab_Knob("OKLCHGrade", "OKLCH Grade"))

    for (name, label, target) in all_defs:
        # Insert a divider + annotation before the hue-band section.
        if name == _HUE_BAND_FIRST and group_node.knob("hue_bands_divider") is None:
            try:
                div = nuke.Text_Knob("hue_bands_divider", "", _HUE_BAND_TOOLTIP)
                group_node.addKnob(div)
            except Exception:
                pass

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

    # Force internal bridge to linear-sRGB
    ocio_in  = group_node.node("OCIOColorSpace_IN")
    ocio_out = group_node.node("OCIOColorSpace_OUT")
    
    if linear_space:
        if ocio_in:
            ocio_in["out_colorspace"].setValue(linear_space)
        if ocio_out:
            ocio_out["in_colorspace"].setValue(linear_space)
        
        wk = _knob(group_node, "working_linear_srgb_space")
        if wk:
            wk.setValue(linear_space)
        _set_text(group_node, "status_text", f"Ready. Working space: {linear_space}")
    else:
        _set_text(
            group_node, "status_text",
            "Note: no linear-sRGB alias found. Using default (check OCIO nodes).",
        )



def initialize_node(node: nuke.Node) -> None:
    """Called from gizmo onCreate: compile kernel, add Link_Knobs, wire OCIO."""
    try:
        # Guard: confirm we have the correct top-level group node
        if _knob(node, "working_linear_srgb_space") is None:
            return

        _hide_tech_knobs(node)

        # 1. Load and compile kernel
        if not _load_kernel_source(node):
            return

        # 2. Add Link_Knobs (param knobs now guaranteed to exist)
        _add_link_knobs(node)

        # 3. Wire OCIO working space
        _setup_working_space(node)

    except Exception as exc:
        _set_text(node, "status_text", f"Init error: {exc}")


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
