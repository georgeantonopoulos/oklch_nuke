"""Initialization and knob-sync helpers for the OKLCH Grade gizmo."""

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

GRADE_KNOBS = (
    "l_gain",
    "l_offset",
    "c_gain",
    "c_offset",
    "hue_shift_deg",
    "mix",
    "clamp_output",
    "bypass",
)

SYNC_KNOBS = set(GRADE_KNOBS) | {
    "input_colorspace",
    "output_colorspace",
    "working_linear_srgb_space",
}


def _knob(node: nuke.Node, name: str):
    return node.knob(name)


def get_ocio_colorspaces() -> List[str]:
    """Return available OCIO colorspaces from the active config."""
    try:
        values = nuke.getOcioColorSpaces()
    except Exception:
        return []

    if not values:
        return []

    # Preserve order while de-duping.
    deduped = []
    seen = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def detect_linear_srgb_space(colorspaces: Iterable[str]) -> Optional[str]:
    """Pick the best linear-sRGB colorspace alias from the active OCIO config."""
    colorspaces = list(colorspaces)

    for alias in LINEAR_SRGB_ALIASES:
        if alias in colorspaces:
            return alias

    lowered = {value.lower(): value for value in colorspaces}
    for alias in LINEAR_SRGB_ALIASES:
        hit = lowered.get(alias.lower())
        if hit:
            return hit

    return None


def _set_enum_values(knob, values: List[str]) -> None:
    if knob is None:
        return
    try:
        knob.setValues(values)
    except Exception:
        pass


def _set_text(node: nuke.Node, knob_name: str, value: str) -> None:
    knob = _knob(node, knob_name)
    if knob is None:
        return
    try:
        knob.setValue(value)
    except Exception:
        pass


def _get_string(node: nuke.Node, knob_name: str) -> str:
    knob = _knob(node, knob_name)
    if knob is None:
        return ""
    try:
        return str(knob.value())
    except Exception:
        return ""


def _get_bool(node: nuke.Node, knob_name: str) -> bool:
    knob = _knob(node, knob_name)
    if knob is None:
        return False
    try:
        return bool(knob.value())
    except Exception:
        return False


def _copy_knob_value(src_node: nuke.Node, dst_node: nuke.Node, knob_name: str) -> None:
    src = _knob(src_node, knob_name)
    dst = _knob(dst_node, knob_name)
    if src is None or dst is None:
        return

    try:
        dst.setValue(src.value())
    except Exception:
        pass


def _hide_tech_knobs(node: nuke.Node) -> None:
    for knob_name in ("working_linear_srgb_space", "diagnostics"):
        knob = _knob(node, knob_name)
        if knob is None:
            continue
        try:
            knob.setFlag(nuke.INVISIBLE)
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

    return None


def _load_kernel_source(group_node: nuke.Node) -> bool:
    blink = group_node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        _set_text(group_node, "status_text", "Error: internal BlinkScript node not found.")
        return False

    kernel_path = _find_kernel_path()
    if not kernel_path:
        _set_text(group_node, "status_text", "Error: oklch_grade_kernel.cpp not found.")
        return False

    try:
        with open(kernel_path, "r", encoding="utf-8") as handle:
            source = handle.read()
    except Exception as exc:
        _set_text(group_node, "status_text", f"Error reading kernel source: {exc}")
        return False

    source_knob = _knob(blink, "kernelSource")
    if source_knob is not None:
        try:
            source_knob.setValue(source)
        except Exception as exc:
            _set_text(group_node, "status_text", f"Error writing kernel source: {exc}")
            return False

    file_knob = _knob(blink, "kernelSourceFile")
    if file_knob is not None:
        try:
            file_knob.setValue(kernel_path)
        except Exception:
            pass

    # Compile if a compile/recompile button is available.
    for compile_knob_name in ("recompile", "compile"):
        compile_knob = _knob(blink, compile_knob_name)
        if compile_knob is not None:
            try:
                compile_knob.execute()
                break
            except Exception:
                continue

    return True


def _sync_internal_nodes(group_node: nuke.Node) -> None:
    in_space = _get_string(group_node, "input_colorspace")
    out_space = _get_string(group_node, "output_colorspace")
    working_space = _get_string(group_node, "working_linear_srgb_space")

    ocio_in = group_node.node("OCIOColorSpace_IN")
    ocio_out = group_node.node("OCIOColorSpace_OUT")
    blink = group_node.node("BlinkScript_OKLCHGrade")

    missing_linear = not bool(working_space)

    if ocio_in is not None:
        if _knob(ocio_in, "in_colorspace") is not None and in_space:
            ocio_in["in_colorspace"].setValue(in_space)
        if _knob(ocio_in, "out_colorspace") is not None and working_space:
            ocio_in["out_colorspace"].setValue(working_space)
        if _knob(ocio_in, "disable") is not None:
            ocio_in["disable"].setValue(missing_linear)

    if ocio_out is not None:
        if _knob(ocio_out, "in_colorspace") is not None and working_space:
            ocio_out["in_colorspace"].setValue(working_space)
        if _knob(ocio_out, "out_colorspace") is not None and out_space:
            ocio_out["out_colorspace"].setValue(out_space)
        if _knob(ocio_out, "disable") is not None:
            ocio_out["disable"].setValue(missing_linear)

    if blink is not None:
        for knob_name in GRADE_KNOBS:
            _copy_knob_value(group_node, blink, knob_name)

        if _knob(blink, "disable") is not None:
            blink["disable"].setValue(missing_linear)


def populate_knobs(node: nuke.Node) -> None:
    """Populate public colorspace menus and set working-space diagnostics."""
    colorspaces = get_ocio_colorspaces()

    in_knob = _knob(node, "input_colorspace")
    out_knob = _knob(node, "output_colorspace")

    _set_enum_values(in_knob, colorspaces)
    _set_enum_values(out_knob, colorspaces)

    linear_space = detect_linear_srgb_space(colorspaces)
    _set_text(node, "working_linear_srgb_space", linear_space or "")

    if colorspaces:
        current_in = _get_string(node, "input_colorspace")
        if current_in not in colorspaces:
            node["input_colorspace"].setValue(colorspaces[0])

        current_out = _get_string(node, "output_colorspace")
        if current_out not in colorspaces:
            node["output_colorspace"].setValue(colorspaces[0])

    if linear_space:
        _set_text(node, "status_text", f"Ready. Working space: {linear_space}")
    else:
        _set_text(
            node,
            "status_text",
            "Warning: no linear-sRGB alias found in OCIO config. Bypass enabled fail-safe.",
        )
        bypass_knob = _knob(node, "bypass")
        if bypass_knob is not None:
            bypass_knob.setValue(True)


def initialize_node(node: nuke.Node) -> None:
    """Call on create/load to configure menus, kernel, and internal links."""
    _hide_tech_knobs(node)
    populate_knobs(node)
    _load_kernel_source(node)
    _sync_internal_nodes(node)


def handle_knob_changed(node: nuke.Node, changed_knob) -> None:
    """Sync internals whenever relevant public knobs are edited."""
    if changed_knob is None:
        return

    knob_name = changed_knob.name()
    if knob_name not in SYNC_KNOBS:
        return

    # Rebuild menu context if a colorspace menu changed.
    if knob_name in {"input_colorspace", "output_colorspace"}:
        populate_knobs(node)

    _sync_internal_nodes(node)
