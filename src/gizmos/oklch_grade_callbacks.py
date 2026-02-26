"""Runtime callbacks for robust OKLCH gizmo initialization in Nuke."""

from __future__ import annotations

import os
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

_KERNEL_SOURCE_RELATIVE = os.path.join("blink", "oklch_grade_kernel.cpp")


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


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_value(node: Optional[nuke.Node]) -> str:
    status = _knob(node, "status_text")
    if status is None:
        return ""
    try:
        return str(status.value())
    except Exception:
        return ""


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


def _missing_param_knobs(blink: Optional[nuke.Node]) -> list[str]:
    if blink is None:
        return [internal_name for _, _, internal_name, _ in _PARAM_LINKS]
    missing: list[str] = []
    for _, label, internal_name, _ in _PARAM_LINKS:
        if _resolve_blink_knob_name(blink, label, internal_name) is None:
            missing.append(internal_name)
    return missing


def _run_recompile(blink: Optional[nuke.Node]) -> None:
    recompile = _knob(blink, "recompile")
    if recompile is None:
        return
    try:
        recompile.execute()
    except Exception:
        # Keep panel responsive even if compile fails.
        pass


def _set_kernel_source_inline_from_file(blink: Optional[nuke.Node]) -> bool:
    """Fallback for older Blink builds where file-mode may not materialize params."""
    if blink is None:
        return False
    kernel_source = _knob(blink, "kernelSource")
    if kernel_source is None:
        return False
    kernel_path = _find_kernel_absolute_path()
    if not kernel_path:
        return False
    try:
        with open(kernel_path, "r", encoding="utf-8") as handle:
            source = handle.read()
    except Exception:
        return False
    try:
        kernel_source.setValue(source)
        return True
    except Exception:
        return False


def _run_reload_kernel_source_file(blink: Optional[nuke.Node]) -> None:
    reload_knob = _knob(blink, "reloadKernelSourceFile")
    if reload_knob is None:
        return
    try:
        reload_knob.execute()
    except Exception:
        pass


def _find_kernel_absolute_path() -> Optional[str]:
    override = os.environ.get("OKLCH_GRADE_KERNEL_PATH", "").strip()
    if override and os.path.isfile(override):
        return os.path.abspath(override)

    here = os.path.abspath(os.path.dirname(__file__))
    # callbacks.py lives in .../gizmos, kernel is in sibling ../blink
    candidate = os.path.normpath(os.path.join(here, "..", _KERNEL_SOURCE_RELATIVE))
    if os.path.isfile(candidate):
        return candidate

    # Fallback for installs where plugin paths vary (repo root, src, gizmos).
    for plugin_path in nuke.pluginPath() or []:
        plugin_path = os.path.abspath(plugin_path)
        candidates = (
            os.path.join(plugin_path, _KERNEL_SOURCE_RELATIVE),
            os.path.join(plugin_path, "..", _KERNEL_SOURCE_RELATIVE),
            os.path.join(plugin_path, "..", "src", _KERNEL_SOURCE_RELATIVE),
        )
        for path in candidates:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                return path

    return None


def _set_kernel_source_file_absolute(blink: Optional[nuke.Node]) -> bool:
    """Set kernelSourceFile in file-mode using absolute path.

    Returns True when a path was set.
    """
    kernel_source_file = _knob(blink, "kernelSourceFile")
    if kernel_source_file is None:
        return False

    kernel_path = _find_kernel_absolute_path()
    if not kernel_path:
        return False

    try:
        current = os.path.normpath(str(kernel_source_file.value()))
    except Exception:
        current = ""

    if current == os.path.normpath(kernel_path):
        return False

    try:
        kernel_source_file.setValue(kernel_path)
        return True
    except Exception:
        return False


def _kernel_source_file_value(blink: Optional[nuke.Node]) -> str:
    kernel_source_file = _knob(blink, "kernelSourceFile")
    if kernel_source_file is None:
        return ""
    try:
        return str(kernel_source_file.value())
    except Exception:
        return ""


def _is_kernel_source_file_mode(blink: Optional[nuke.Node], kernel_path: str) -> bool:
    if not kernel_path:
        return False
    current_raw = _kernel_source_file_value(blink)
    if not current_raw:
        return False
    try:
        current = os.path.normpath(current_raw)
    except Exception:
        return False
    return current == os.path.normpath(kernel_path)


def _apply_legacy_blink_compat(blink: Optional[nuke.Node]) -> bool:
    """Apply pre-16 Blink compatibility. Returns True when state changed."""
    if blink is None or _nuke_major_version() >= 16:
        return False

    changed = False

    for baked_name in ("isBaked", "isbaked"):
        baked_knob = _knob(blink, baked_name)
        if baked_knob is not None:
            try:
                current = bool(baked_knob.value())
            except Exception:
                current = True
            if current:
                try:
                    baked_knob.setValue(False)
                    changed = True
                except Exception:
                    pass
            break
    for kernel_name in ("KernelDescription", "kernelDescription"):
        kernel_desc_knob = _knob(blink, kernel_name)
        if kernel_desc_knob is not None:
            try:
                current = str(kernel_desc_knob.value())
            except Exception:
                current = "nonempty"
            if current:
                try:
                    # Empty value so legacy Nuke saves without embedded KernelDescription payload.
                    kernel_desc_knob.setValue("")
                    changed = True
                except Exception:
                    pass
            break
    return changed


def _needs_legacy_recompile(blink: Optional[nuke.Node]) -> bool:
    """True when legacy mode is active, even if no value changed this pass."""
    if blink is None or _nuke_major_version() >= 16:
        return False

    for kernel_name in ("KernelDescription", "kernelDescription"):
        kernel_desc_knob = _knob(blink, kernel_name)
        if kernel_desc_knob is not None:
            try:
                if str(kernel_desc_knob.value()):
                    return True
            except Exception:
                return True
            return False
    return False


def _prepare_blink_params(node: Optional[nuke.Node], force_recompile: bool) -> tuple[Optional[nuke.Node], list[str]]:
    """Ensure Blink param knobs exist before linking group knobs."""
    if node is None:
        return None, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        return None, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    kernel_path = _find_kernel_absolute_path()
    if not kernel_path:
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> "
                "Kernel file not found. Expected oklch_grade_kernel.cpp in the install tree."
                "</small></font>"
            ),
        )
        return blink, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    # Nuke < 16: file-mode compile does not reliably materialize param knobs,
    # and isBaked/KernelDescription from a Nuke 16 gizmo cannot be cleared at
    # runtime.  Go straight to inline kernelSource (read .cpp, set knob value,
    # recompile).
    if _nuke_major_version() < 16:
        if _set_kernel_source_inline_from_file(blink):
            _run_recompile(blink)
        missing = _missing_param_knobs(blink)
        return blink, missing

    # Nuke >= 16: file-mode path works reliably.
    kernel_file_changed = _set_kernel_source_file_absolute(blink)
    kernel_file_mode = _is_kernel_source_file_mode(blink, kernel_path)
    if not kernel_file_mode:
        current = _escape_html(_kernel_source_file_value(blink) or "<empty>")
        target = _escape_html(kernel_path)
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> "
                f"Could not set absolute kernelSourceFile. current={current} target={target}"
                "</small></font>"
            ),
        )
        return blink, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    if kernel_file_changed or force_recompile:
        _run_reload_kernel_source_file(blink)
        _run_recompile(blink)

    missing = _missing_param_knobs(blink)

    return blink, missing


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

    blink, missing = _prepare_blink_params(node, force_recompile=force_recompile)
    if blink is None:
        _set_status(
            node,
            "<font color='#cc6666'><small><b>Status:</b> BlinkScript node not ready yet.</small></font>",
        )
        return len(_PARAM_LINKS)

    if missing:
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> Blink kernel params missing after compile: "
                f"{', '.join(missing[:6])}{'...' if len(missing) > 6 else ''}.</small></font>"
            ),
        )
        return len(_PARAM_LINKS)

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
    _apply_colorspace_defaults(node)
    unresolved = _sync_links(node, force_recompile=True)
    if unresolved:
        # One more forced pass for legacy setups where params appear after
        # first compile/reload cycle.
        unresolved = _sync_links(node, force_recompile=True)
    if unresolved:
        if "#cc6666" in _status_value(node).lower():
            return
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
    unresolved = _sync_links(node, force_recompile=False)
    if unresolved:
        _sync_links(node, force_recompile=True)
