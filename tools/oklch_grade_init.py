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

# NO_RERENDER flag — prevents divider knobs from dirtying the node hash.
_NO_RERENDER = 0x0000000000004000

# Used only by _add_link_knobs — order determines panel appearance.
# Tuples: (knob_name, label, link_target).
#
# Divider entries:  name='', label='', target=None
#   → emits Text_Knob('', '') which Nuke draws as a horizontal rule.
#
# Content entries:  name=<str>, label='', target=None
#   → emits a named Text_Knob carrying text/tooltip (e.g. hue_bands_divider).
#
# Link entries:     name=<str>, label=<str>, target=<str>
#   → emits a Link_Knob pointing at the given internal knob.
_GRADE_LINK_DEFS = (
    # --- Lightness & Chroma ---
    ("l_gain",               "L Gain",               "BlinkScript_OKLCHGrade.l_gain"),
    ("l_offset",             "L Offset",             "BlinkScript_OKLCHGrade.l_offset"),
    ("l_contrast",           "L Contrast",           "BlinkScript_OKLCHGrade.l_contrast"),
    ("l_pivot",              "L Pivot",              "BlinkScript_OKLCHGrade.l_pivot"),
    ("c_gain",               "C Gain",               "BlinkScript_OKLCHGrade.c_gain"),
    ("c_offset",             "C Offset",             "BlinkScript_OKLCHGrade.c_offset"),
    ("",                     "",                     None),  # ── divider ──
    # --- Global Hue ---
    ("hue_shift_deg",        "Hue Shift (deg)",      "BlinkScript_OKLCHGrade.hue_shift_deg"),
    ("hue_chroma_threshold", "Hue Chroma Threshold", "BlinkScript_OKLCHGrade.hue_chroma_threshold"),
    ("",                     "",                     None),  # ── divider ──
    # --- Hue Band Selectors (named content block, carries tooltip text) ---
    ("hue_bands_divider",    "",                     None),
    ("hue_shift_red",        "Hue Shift Red",        "BlinkScript_OKLCHGrade.hue_shift_red"),
    ("hue_shift_yellow",     "Hue Shift Yellow",     "BlinkScript_OKLCHGrade.hue_shift_yellow"),
    ("hue_shift_green",      "Hue Shift Green",      "BlinkScript_OKLCHGrade.hue_shift_green"),
    ("hue_shift_cyan",       "Hue Shift Cyan",       "BlinkScript_OKLCHGrade.hue_shift_cyan"),
    ("hue_shift_blue",       "Hue Shift Blue",       "BlinkScript_OKLCHGrade.hue_shift_blue"),
    ("hue_shift_magenta",    "Hue Shift Magenta",    "BlinkScript_OKLCHGrade.hue_shift_magenta"),
    ("hue_target_deg",       "Hue Target (deg)",      "BlinkScript_OKLCHGrade.hue_target_deg"),
    ("hue_target_shift",     "Hue Target Shift",      "BlinkScript_OKLCHGrade.hue_target_shift"),
    ("hue_target_falloff_deg", "Hue Target Falloff",   "BlinkScript_OKLCHGrade.hue_target_falloff_deg"),
    ("",                     "",                     None),  # ── divider ──
    # --- Utilities ---
    ("mix",                  "Mix",                  "BlinkScript_OKLCHGrade.mix"),
    ("clamp_output",         "Clamp Output",         "BlinkScript_OKLCHGrade.clamp_output"),
    ("bypass",               "Bypass",               "BlinkScript_OKLCHGrade.bypass"),
    ("debug_mode",           "Debug Mode",           "BlinkScript_OKLCHGrade.debug_mode"),
)

# Slider ranges for BlinkScript float params.
# defineParam(name, label, default) has no min/max argument in the Blink API,
# so Nuke assigns a default range (often -1..1 or 0..1) after compilation.
# These must be applied via setRange() after recompile.execute().
_PARAM_RANGES = {
    # Lightness
    "l_gain":               (0.0,    3.0),
    "l_offset":             (-1.0,   1.0),
    "l_contrast":           (0.0,    3.0),
    "l_pivot":              (0.0,    1.0),
    # Chroma
    "c_gain":               (0.0,    2.0),
    "c_offset":             (-0.5,   0.5),
    # Global hue
    "hue_shift_deg":      (-360.0, 360.0),
    # Chroma threshold: 0 = shift everything, 0.2 = aggressive grey protection.
    # OKLCH chroma for sRGB colours typically spans 0..~0.37; a threshold of
    # 0.05 protects near-neutral values while leaving saturated colours free.
    "hue_chroma_threshold": (0.0,    0.2),
    # Hue band selectors — same degree range as global shift
    "hue_shift_red":        (-180.0, 180.0),
    "hue_shift_yellow":     (-180.0, 180.0),
    "hue_shift_green":      (-180.0, 180.0),
    "hue_shift_cyan":       (-180.0, 180.0),
    "hue_shift_blue":       (-180.0, 180.0),
    "hue_shift_magenta":    (-180.0, 180.0),
    "hue_target_deg":      (0.0,    360.0),
    "hue_target_shift":      (-180.0, 180.0),
    "hue_target_falloff_deg":    (1.0,    180.0),
    # Utilities
    "mix":                  (0.0,    1.0),
}

_COLORSPACE_LINK_DEFS = (
    ("input_colorspace",  "Input Colorspace",  "OCIOColorSpace_IN.in_colorspace"),
    ("output_colorspace", "Output Colorspace", "OCIOColorSpace_OUT.out_colorspace"),
    ("",                  "",                  None),  # ── divider ──
)


def _knob(node: nuke.Node, name: str):
    return node.knob(name)


def _is_oklch_group_node(node: nuke.Node) -> bool:
    """Return True when `node` is the top-level OKLCH gizmo Group."""
    try:
        return node is not None and node.Class() == "Group"
    except Exception:
        return False


def _ensure_base_knobs(group_node: nuke.Node) -> None:
    """Ensure the main tab and foundational public/tech knobs exist.

    The `OKLCH Grade` tab, `status_text`, and `working_linear_srgb_space` are
    created here (at runtime) so all subsequently added controls share the same
    tab ownership model. Mixing static gizmo-defined knobs with dynamic
    addKnob() calls can cause runtime-added knobs to land in `User`.
    """
    if group_node.knob("OKLCHGrade") is None:
        group_node.addKnob(nuke.Tab_Knob("OKLCHGrade", "OKLCH Grade"))

    if group_node.knob("status_text") is None:
        group_node.addKnob(nuke.Text_Knob("status_text", "Status", "Initializing..."))

    if group_node.knob("working_linear_srgb_space") is None:
        wk = nuke.String_Knob("working_linear_srgb_space", "Working Linear sRGB")
        wk.setValue("")
        group_node.addKnob(wk)


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


def _has_link_knobs(node: nuke.Node) -> bool:
    """Return True when main runtime link knobs were added."""
    return _knob(node, "input_colorspace") is not None


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
        _set_text(group_node, "status_text", "Waiting: BlinkScript node not ready yet.")
        return False

    kernel_path = _find_kernel_path()
    if not kernel_path:
        _set_text(group_node, "status_text", "Error: oklch_grade_kernel.cpp not found.")
        return False

    # Read the kernel source in Python and write it to the inline kernelSource
    # knob.  Using kernelSourceFile would switch the BlinkScript node to file
    # mode, causing it to ignore the inline text and leaving the kernel
    # uncompiled (no param knobs appear, no Link_Knobs can be targeted).
    try:
        with open(kernel_path, "r") as fh:
            source = fh.read()
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error reading kernel file: {exc}")
        return False

    ks = _knob(blink, "kernelSource")
    if ks is None:
        _set_text(group_node, "status_text", "Error: kernelSource knob not found on BlinkScript node.")
        return False

    try:
        ks.setValue(source)
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error setting kernel source: {exc}")
        return False

    # Recompile is synchronous — knobs exist immediately after
    compile_button = _knob(blink, "recompile")
    if compile_button is None:
        _set_text(group_node, "status_text", "Error: recompile knob not found on BlinkScript node.")
        return False
    compile_button.execute()

    # Check if compilation succeeded by looking for the first param knob
    if _knob(blink, "l_gain") is None:
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


def _add_link_knobs(group_node: nuke.Node) -> None:
    """Add Link_Knobs that directly reference internal node knobs.

    Must be called after _load_kernel_source so the BlinkScript kernel param
    knobs exist.

    Re-entry guard: if the first named link knob (input_colorspace) already
    exists on the node, all knobs — including the anonymous dividers that
    cannot be found by name — were already added.  Bail out immediately.

    Link_Knob is bidirectional, updates instantly at eval time with no Python
    overhead, and preserves the correct widget type (checkbox stays a checkbox,
    not an expression field).
    """
    # Fast re-entry guard — unnamed dividers can't be found by knob(), so we
    # use the first named knob as a proxy for the whole block.
    if group_node.knob("input_colorspace") is not None:
        return

    all_defs = _COLORSPACE_LINK_DEFS + _GRADE_LINK_DEFS

    # Add the tab only if it doesn't already exist.
    # Calling addKnob with a Tab_Knob whose name already exists creates a
    # *duplicate* tab rather than selecting the existing one, which produces
    # two "OKLCH Grade" tabs — one holding status_text and one holding the
    # link knobs added below.
    if group_node.knob("OKLCHGrade") is None:
        group_node.addKnob(nuke.Tab_Knob("OKLCHGrade", "OKLCH Grade"))

    for (name, label, target) in all_defs:
        if target is None:
            if name == "":
                # True horizontal-rule divider: empty name AND empty label.
                # Text_Knob('', '') is what Nuke uses for its own "Divider Line"
                # control.  NO_RERENDER stops it from dirtying the node hash.
                try:
                    div = nuke.Text_Knob("", "")
                    div.setFlag(_NO_RERENDER)
                    group_node.addKnob(div)
                except Exception:
                    pass
            else:
                # Named content block (e.g. hue_bands_divider tooltip).
                # Skip if already present.
                if group_node.knob(name) is not None:
                    continue
                text_value = _HUE_BAND_TOOLTIP if name == "hue_bands_divider" else ""
                try:
                    group_node.addKnob(nuke.Text_Knob(name, "", text_value))
                except Exception:
                    pass
        else:
            # Named Link_Knob — skip if already present.
            if group_node.knob(name) is not None:
                continue
            try:
                lk = nuke.Link_Knob(name, label)
                lk.setLink(target)
                group_node.addKnob(lk)
            except Exception:
                pass


def _setup_working_space(group_node: nuke.Node) -> None:
    """Wire internal OCIO bridge to a fixed scene-linear working space.

    The public gizmo knobs remain linked to:
    - OCIOColorSpace_IN.in_colorspace
    - OCIOColorSpace_OUT.out_colorspace

    Internal bridge knobs are deterministic and do not depend on parent
    expressions:
    - OCIOColorSpace_IN.out_colorspace = scene_linear
    - OCIOColorSpace_OUT.in_colorspace = scene_linear
    """
    fixed_space = "scene_linear"
    ocio_in = group_node.node("OCIOColorSpace_IN")
    ocio_out = group_node.node("OCIOColorSpace_OUT")

    if ocio_in:
        ocio_in["out_colorspace"].setValue(fixed_space)
    if ocio_out:
        ocio_out["in_colorspace"].setValue(fixed_space)

    wk = _knob(group_node, "working_linear_srgb_space")
    if wk:
        wk.setValue(fixed_space)
    _set_text(group_node, "status_text", f"Ready. Working space: {fixed_space}")



def initialize_node(node: nuke.Node) -> None:
    """Called from gizmo onCreate: compile kernel, add Link_Knobs, wire OCIO."""
    try:
        # Guard: confirm we have the correct top-level group node.
        if not _is_oklch_group_node(node):
            return

        _ensure_base_knobs(node)
        _hide_tech_knobs(node)

        # Already initialized; keep this idempotent for repeated callbacks.
        if _has_link_knobs(node):
            return

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
    if not _is_oklch_group_node(node):
        return
    # Retry initialization if onCreate ran before Blink internals were ready.
    if not _has_link_knobs(node):
        initialize_node(node)


def initialize_this_node() -> None:
    """Safe onCreate entrypoint used directly from the gizmo callback."""
    try:
        node = nuke.thisNode()
        initialize_node(node)
    except Exception as exc:
        try:
            node = nuke.thisNode()
            k = node.knob("status_text") if node else None
            if k is not None:
                k.setValue(f"Init callback error: {exc}")
        except Exception:
            pass


def handle_this_knob_changed() -> None:
    """Safe knobChanged entrypoint used directly from the gizmo callback."""
    try:
        node = nuke.thisNode()
        knob = nuke.thisKnob()
        handle_knob_changed(node, knob)
    except Exception:
        # Keep knobChanged silent, but never break the node panel.
        pass
