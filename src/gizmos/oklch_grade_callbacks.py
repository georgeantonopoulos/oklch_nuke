"""Runtime callbacks for robust OKLCH gizmo initialization in Nuke."""

from __future__ import annotations

from typing import Optional

import nuke

# (public knob name, Blink label, internal var name, optional (min, max) range)
_PARAM_LINKS = (
    ("l_gain", "L Gain", "l_gain", (0.0, 3.0)),
    ("l_offset", "L Offset", "l_offset", (-1.0, 1.0)),
    ("l_contrast", "L Contrast", "l_contrast", (0.0, 3.0)),
    ("l_pivot", "L Pivot", "l_pivot", (0.0, 1.0)),
    ("c_gain", "C Gain", "c_gain", (0.0, 2.0)),
    ("c_offset", "C Offset", "c_offset", (-0.5, 0.5)),
    ("hue_shift_deg", "Hue Shift (deg)", "hue_shift_deg", (-360.0, 360.0)),
    ("hue_chroma_threshold", "Hue Chroma Threshold", "hue_chroma_threshold", (0.0, 0.2)),
    ("hue_shift_red", "Hue Shift Red", "hue_shift_red", (-180.0, 180.0)),
    ("hue_shift_yellow", "Hue Shift Yellow", "hue_shift_yellow", (-180.0, 180.0)),
    ("hue_shift_green", "Hue Shift Green", "hue_shift_green", (-180.0, 180.0)),
    ("hue_shift_cyan", "Hue Shift Cyan", "hue_shift_cyan", (-180.0, 180.0)),
    ("hue_shift_blue", "Hue Shift Blue", "hue_shift_blue", (-180.0, 180.0)),
    ("hue_shift_magenta", "Hue Shift Magenta", "hue_shift_magenta", (-180.0, 180.0)),
    ("hue_target_deg", "Hue Target (deg)", "hue_target_deg", (0.0, 360.0)),
    ("hue_target_shift", "Hue Target Shift", "hue_target_shift", (-180.0, 180.0)),
    ("hue_target_falloff_deg", "Hue Target Falloff", "hue_target_falloff_deg", (1.0, 180.0)),
    ("mix", "Mix", "mix", (0.0, 1.0)),
    ("clamp_output", "Clamp Output", "clamp_output", None),
    ("bypass", "Bypass", "bypass", None),
    ("debug_mode", "Debug Mode", "debug_mode", None),
)


def _nuke_major_version() -> int:
    try:
        return int(getattr(nuke, "NUKE_VERSION_MAJOR", 0))
    except Exception:
        return 0


def _knob(node: Optional[nuke.Node], name: str):
    if node is None:
        return None
    try:
        return node.knob(name)
    except Exception:
        return None


def _set_status(node: Optional[nuke.Node], html: str) -> None:
    status = _knob(node, "status_text")
    if status is None:
        return
    try:
        status.setValue(html)
    except Exception:
        pass


def _resolve_blink_knob_name(blink: nuke.Node, label: str, internal_name: str) -> Optional[str]:
    # Handle both Blink naming styles seen in the wild:
    # 1) Internal var name: l_gain
    # 2) Label-derived: OKLCHGrade_L Gain / OKLCHGrade_L_Gain
    candidates = (
        internal_name,
        f"OKLCHGrade_{label}",
        f"OKLCHGrade_{label.replace(' ', '_')}",
    )
    for candidate in candidates:
        if _knob(blink, candidate) is not None:
            return candidate
    return None


def _run_recompile(blink: Optional[nuke.Node]) -> None:
    recompile = _knob(blink, "recompile")
    if recompile is None:
        return
    try:
        recompile.execute()
    except Exception:
        # Keep panel responsive even if compile fails.
        pass


def _apply_legacy_blink_compat(node: Optional[nuke.Node]) -> None:
    if node is None or _nuke_major_version() >= 16:
        return

    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        return

    for baked_name in ("isBaked", "isbaked"):
        baked_knob = _knob(blink, baked_name)
        if baked_knob is not None:
            try:
                baked_knob.setValue(False)
            except Exception:
                pass
            break

    for kernel_name in ("KernelDescription", "kernelDescription"):
        kernel_desc_knob = _knob(blink, kernel_name)
        if kernel_desc_knob is not None:
            try:
                # Empty value so legacy Nuke saves without embedded KernelDescription payload.
                kernel_desc_knob.setValue("")
            except Exception:
                pass
            break


def _apply_colorspace_defaults(node: Optional[nuke.Node]) -> None:
    if node is None:
        return

    spaces = nuke.getOcioColorSpaces() or []
    aliases = ("Utility - Linear - sRGB", "lin_srgb", "Linear sRGB", "srgb_linear")

    working = ""
    for alias in aliases:
        if alias in spaces:
            working = alias
            break

    if not working:
        lowered = {value.lower(): value for value in spaces}
        for alias in aliases:
            hit = lowered.get(alias.lower())
            if hit:
                working = hit
                break

    if not working:
        for value in spaces:
            low = value.lower()
            if "linear" in low and "srgb" in low:
                working = value
                break

    status = (
        "<font color='#777777'><small><b>Status:</b> Note: no linear-sRGB alias found. "
        "Falling back to scene_linear.</small></font>"
    )
    if working:
        wk = _knob(node, "working_linear_srgb_space")
        if wk is not None:
            try:
                wk.setValue(working)
            except Exception:
                pass
        safe = working.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        status = f"<font color='#66AA66'><small><b>Status:</b> OK (working space: {safe})</small></font>"

    _set_status(node, status)


def _sync_links(node: Optional[nuke.Node], force_recompile: bool) -> int:
    """Resolve and set link targets. Returns number of unresolved controls."""
    if node is None:
        return 0

    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        _set_status(
            node,
            "<font color='#cc6666'><small><b>Status:</b> BlinkScript node not ready yet.</small></font>",
        )
        return len(_PARAM_LINKS)

    if force_recompile:
        _run_recompile(blink)

    unresolved = 0
    for public_name, label, internal_name, value_range in _PARAM_LINKS:
        public_knob = _knob(node, public_name)
        if public_knob is None:
            continue

        if value_range is not None:
            lo, hi = value_range
            try:
                public_knob.setRange(lo, hi)
            except Exception:
                pass

        resolved_name = _resolve_blink_knob_name(blink, label, internal_name)
        if not resolved_name:
            unresolved += 1
            continue

        blink_knob = _knob(blink, resolved_name)
        if value_range is not None and blink_knob is not None:
            lo, hi = value_range
            try:
                blink_knob.setRange(lo, hi)
            except Exception:
                pass

        try:
            public_knob.setLink(f"BlinkScript_OKLCHGrade.{resolved_name}")
        except Exception:
            unresolved += 1

    return unresolved


def initialize_this_node() -> None:
    node = nuke.thisNode()
    _apply_legacy_blink_compat(node)
    unresolved = _sync_links(node, force_recompile=True)
    if unresolved:
        # One more pass after recompile for setups that materialize knobs lazily.
        unresolved = _sync_links(node, force_recompile=False)
    _apply_colorspace_defaults(node)
    if unresolved:
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> "
                f"{unresolved} linked controls are unresolved. Open BlinkScript node and click Recompile."
                "</small></font>"
            ),
        )


def handle_this_knob_changed() -> None:
    # Lightweight maintenance pass for script-load or delayed knob materialization.
    node = nuke.thisNode()
    _apply_legacy_blink_compat(node)
    unresolved = _sync_links(node, force_recompile=False)
    if unresolved:
        _sync_links(node, force_recompile=True)
