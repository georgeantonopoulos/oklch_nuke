"""Runtime callbacks for robust OKLCH gizmo initialization in Nuke.

All public entrypoints (initialize_this_node, handle_this_knob_changed) are
wrapped in top-level try/except so that a callback failure never crashes Nuke.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Optional

import nuke

# (public knob name, Blink label, internal var name, optional (min, max) range)
_PARAM_LINKS = (
    ("l_gain", "l_gain", "l_gain", (0.0, 3.0)),
    ("l_offset", "l_offset", "l_offset", (-1.0, 1.0)),
    ("l_contrast", "l_contrast", "l_contrast", (0.0, 3.0)),
    ("l_pivot", "l_pivot", "l_pivot", (0.0, 1.0)),
    ("c_gain", "c_gain", "c_gain", (0.0, 2.0)),
    ("c_offset", "c_offset", "c_offset", (-0.5, 0.5)),
    ("hue_shift_deg", "hue_shift_deg", "hue_shift_deg", (-360.0, 360.0)),
    ("hue_chroma_threshold", "hue_chroma_threshold", "hue_chroma_threshold", (0.0, 0.2)),
    ("hue_shift_red", "hue_shift_red", "hue_shift_red", (-180.0, 180.0)),
    ("hue_shift_yellow", "hue_shift_yellow", "hue_shift_yellow", (-180.0, 180.0)),
    ("hue_shift_green", "hue_shift_green", "hue_shift_green", (-180.0, 180.0)),
    ("hue_shift_cyan", "hue_shift_cyan", "hue_shift_cyan", (-180.0, 180.0)),
    ("hue_shift_blue", "hue_shift_blue", "hue_shift_blue", (-180.0, 180.0)),
    ("hue_shift_magenta", "hue_shift_magenta", "hue_shift_magenta", (-180.0, 180.0)),
    ("hue_target_deg", "hue_target_deg", "hue_target_deg", (0.0, 360.0)),
    ("hue_target_shift", "hue_target_shift", "hue_target_shift", (-180.0, 180.0)),
    ("hue_target_falloff_deg", "hue_target_falloff_deg", "hue_target_falloff_deg", (1.0, 180.0)),
    ("hue_curves_enable", "hue_curves_enable", "hue_curves_enable", None),
    ("mix", "mix", "mix", (0.0, 1.0)),
    ("clamp_output", "clamp_output", "clamp_output", None),
    ("bypass", "bypass", "bypass", None),
    ("debug_mode", "debug_mode", "debug_mode", None),
)

# Knobs that actually require a re-sync when changed.  All others (slider
# drags on linked params, UI cosmetic knobs) are ignored by knobChanged to
# avoid expensive re-entrancy and unnecessary Blink recompiles.
_KNOBS_NEEDING_SYNC = frozenset({
    "hue_curves_enable",
    "hue_curve_data",
    "input_colorspace",
    "output_colorspace",
    "showPanel",         # panel open — triggers updateValue on PyCustom widgets
})

# Lightweight knobs update runtime LUT state only (no compile/reload path).
_LIGHTWEIGHT_SYNC_KNOBS = frozenset({
    "hue_curves_enable",
    "hue_curve_data",
    "showPanel",
})

try:
    import hue_curve_data as _hcd
except Exception:
    _hcd = None  # type: ignore[assignment]

# Re-entrancy guard: prevents nested knobChanged → setValue → knobChanged
# cascades that can crash Nuke.
_in_callback = False

_KERNEL_SOURCE_RELATIVE = os.path.join("blink", "oklch_grade_kernel.cpp")
_DEBUG_ENV = "OKLCH_GRADE_DEBUG"
_DEBUG_LOG_ENV = "OKLCH_GRADE_DEBUG_LOG"
_DEBUG_FILE = os.path.expanduser("~/.nuke/oklch_debug_on.txt")
_DEBUG_DEFAULT_LOG = "/tmp/oklch_grade_callbacks.log"
_DEBUG_ALWAYS = False
_CALLBACK_NODE_HINT = ""


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


_debug_knob_active = False


def _check_debug_knob(node: Optional[nuke.Node]) -> None:
    """Activate module-level debug if the gizmo's debug_callbacks knob is on."""
    global _debug_knob_active
    if node is None:
        return
    try:
        k = node.knob("debug_callbacks")
        if k is not None and k.value():
            _debug_knob_active = True
    except Exception:
        pass


def _debug_enabled() -> bool:
    if _DEBUG_ALWAYS or _debug_knob_active:
        return True
    if _is_truthy(os.environ.get(_DEBUG_ENV, "")):
        return True
    try:
        return os.path.isfile(_DEBUG_FILE)
    except Exception:
        return False


def _debug_log_path() -> str:
    env_path = os.environ.get(_DEBUG_LOG_ENV, "").strip()
    if env_path:
        return env_path
    return _DEBUG_DEFAULT_LOG


def _node_name(node: Optional[nuke.Node]) -> str:
    if node is None:
        return "<none>"
    try:
        return str(node.fullName())
    except Exception:
        try:
            return str(node.name())
        except Exception:
            return "<unknown>"


def set_callback_node_hint(node: Optional[nuke.Node]) -> None:
    """Record likely owner node for callback contexts where thisNode() is absent."""
    global _CALLBACK_NODE_HINT
    if node is None:
        _CALLBACK_NODE_HINT = ""
        return
    try:
        _CALLBACK_NODE_HINT = str(node.fullName())
        return
    except Exception:
        pass
    try:
        _CALLBACK_NODE_HINT = str(node.name())
    except Exception:
        _CALLBACK_NODE_HINT = ""


def _debug(message: str, *, node: Optional[nuke.Node] = None, error: Optional[Exception] = None) -> None:
    if not _debug_enabled():
        return
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] pid={os.getpid()} node={_node_name(node)} {message}"
    if error is not None:
        line += f" error={error!r}"
    try:
        if hasattr(nuke, "tprint"):
            nuke.tprint(f"[OKLCH Callbacks] {line}")
        else:
            print(f"[OKLCH Callbacks] {line}")
    except Exception:
        pass

    log_path = _debug_log_path()
    if not log_path:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _diag_dump(label: str, node: Optional[nuke.Node]) -> None:
    """Dump key knob values and link state for debugging persistence."""
    if not _debug_enabled() or node is None:
        return
    lines = [f"DIAG[{label}]"]
    for kname in ("l_gain", "l_offset", "hue_shift_deg", "hue_shift_red", "c_gain"):
        k = _knob(node, kname)
        if k is None:
            lines.append(f"  {kname}: MISSING_ON_GIZMO")
            continue
        try:
            val = k.value()
        except Exception:
            val = "<err>"
        try:
            link = k.getLink(0) or "<no-link>"
        except Exception:
            link = "<err>"
        lines.append(f"  {kname}: val={val} link={link}")
    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is not None:
        try:
            names = [blink.knob(i).name() for i in range(blink.numKnobs())]
            params = [n for n in names if not n.startswith(("name", "xpos", "ypos",
                "tile_color", "note_font", "selected", "hide_input", "cached",
                "disable", "dope_sheet", "gl_color", "label", "icon", "postage",
                "lifetime", "useLifetime", "indicators", "process_mask", "channel",
                "kernelSource", "recompile", "rebuild", "maxGPU", "maxTile",
                "ProgramGroup", "KernelDesc", "kernelDesc", "isBaked",
                "kernelSourceFile",
            ))]
            lines.append(f"  BLINK_KNOBS: {params}")
        except Exception as exc:
            lines.append(f"  BLINK_KNOBS: <err: {exc}>")
    _debug("\\n".join(lines), node=node)


def _nuke_major_version() -> int:
    try:
        return int(getattr(nuke, "NUKE_VERSION_MAJOR", 0))
    except Exception:
        return 0


_debug(f"module_loaded nuke_major={_nuke_major_version()}", node=None)


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


def _set_blink_param_if_exists(
    blink: Optional[nuke.Node],
    internal_name: str,
    label: str,
    value,
) -> bool:
    if blink is None:
        return False
    resolved = _resolve_blink_knob_name(blink, label, internal_name)
    if not resolved:
        return False
    knob = _knob(blink, resolved)
    if knob is None:
        return False
    try:
        knob.setValue(value)
        return True
    except Exception:
        return False


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
        _debug("blink.recompile executed", node=blink)
    except Exception as exc:
        # Keep panel responsive even if compile fails.
        _debug("blink.recompile failed", node=blink, error=exc)
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
        _debug("blink.reloadKernelSourceFile executed", node=blink)
    except Exception as exc:
        _debug("blink.reloadKernelSourceFile failed", node=blink, error=exc)
        pass


_kernel_path_cache: Optional[str] = None
_kernel_path_cache_override: str = ""


def _find_kernel_absolute_path() -> Optional[str]:
    global _kernel_path_cache, _kernel_path_cache_override
    override = os.environ.get("OKLCH_GRADE_KERNEL_PATH", "").strip()
    if override == _kernel_path_cache_override and _kernel_path_cache is not None:
        return _kernel_path_cache
    _kernel_path_cache_override = override

    if override and os.path.isfile(override):
        _kernel_path_cache = os.path.abspath(override)
        return _kernel_path_cache

    here = os.path.abspath(os.path.dirname(__file__))
    # callbacks.py lives in .../gizmos, kernel is in sibling ../blink
    candidate = os.path.normpath(os.path.join(here, "..", _KERNEL_SOURCE_RELATIVE))
    if os.path.isfile(candidate):
        _kernel_path_cache = candidate
        return _kernel_path_cache

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
                _kernel_path_cache = path
                return _kernel_path_cache

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
    _debug(f"prepare_blink_params start force_recompile={force_recompile}", node=node)
    if node is None:
        return None, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        return None, [internal_name for _, _, internal_name, _ in _PARAM_LINKS]

    kernel_path = _find_kernel_absolute_path()
    if not kernel_path:
        _debug("prepare_blink_params missing kernel path", node=node)
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
        _debug(
            f"prepare_blink_params legacy_mode missing={len(missing)}",
            node=node,
        )
        return blink, missing

    # Nuke >= 16: prefer non-executing path unless param knobs are missing.
    kernel_file_changed = _set_kernel_source_file_absolute(blink)
    kernel_file_mode = _is_kernel_source_file_mode(blink, kernel_path)
    if not kernel_file_mode:
        # Soft-fail: many deployments work via embedded kernelSource and still
        # expose all param knobs correctly.
        current = _escape_html(_kernel_source_file_value(blink) or "<empty>")
        target = _escape_html(kernel_path)
        _debug(
            f"prepare_blink_params kernel file mode mismatch current={current} target={target}",
            node=node,
        )

    missing_before = _missing_param_knobs(blink)
    needs_compile = force_recompile or bool(missing_before)
    if needs_compile:
        if kernel_file_changed:
            _run_reload_kernel_source_file(blink)
        _run_recompile(blink)

    missing = _missing_param_knobs(blink)
    _debug(
        (
            "prepare_blink_params done "
            f"kernel_changed={kernel_file_changed} "
            f"kernel_mode={kernel_file_mode} "
            f"needs_compile={needs_compile} "
            f"missing_before={len(missing_before)} "
            f"missing_after={len(missing)}"
        ),
        node=node,
    )

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


def _ensure_hue_lut_format() -> None:
    try:
        nuke.addFormat("360 1 1 HueLUT_360x1")
    except Exception:
        # Format is likely already present.
        pass


def _ensure_hue_curve_data(node: Optional[nuke.Node], huecorrect: Optional[nuke.Node]) -> None:
    if _hcd is None:
        return
    curve_data_knob = _knob(node, "hue_curve_data")
    if curve_data_knob is None:
        return

    try:
        raw = str(curve_data_knob.value() or "")
    except Exception:
        raw = ""
    if raw.strip():
        return

    migrated = None
    hue_knob = _knob(huecorrect, "hue")
    if hue_knob is not None:
        try:
            migrated = _hcd.parse_hue_script_points(hue_knob.toScript())
        except Exception:
            migrated = None

    points = migrated or list(_hcd._DEFAULT_POINTS)
    try:
        curve_data_knob.setValue(_hcd.points_to_json(points))
    except Exception:
        pass


def _apply_expression_lut_from_data(node: Optional[nuke.Node]) -> bool:
    if node is None or _hcd is None:
        return False
    expr = node.node("Expression_HueRamp")
    if expr is None:
        return False

    curve_data_knob = _knob(node, "hue_curve_data")
    raw = ""
    if curve_data_knob is not None:
        try:
            raw = str(curve_data_knob.value() or "")
        except Exception:
            raw = ""

    points = None
    if raw.strip():
        try:
            points = _hcd.normalize_points(json.loads(raw))
        except Exception:
            points = None
    if not points:
        points = list(_hcd._DEFAULT_POINTS)

    expr_lut = _hcd.points_to_lut_expression(points, x_var="lutx")

    try:
        temp_name0 = _knob(expr, "temp_name0")
        temp_expr0 = _knob(expr, "temp_expr0")
        expr0 = _knob(expr, "expr0")
        expr1 = _knob(expr, "expr1")
        expr2 = _knob(expr, "expr2")
        if temp_name0 is not None:
            temp_name0.setValue("lutx")
        if temp_expr0 is not None:
            temp_expr0.setValue("(x + 0.5) / width")
        if expr0 is not None:
            expr0.setValue(expr_lut)
        if expr1 is not None:
            expr1.setValue(expr_lut)
        if expr2 is not None:
            expr2.setValue(expr_lut)
        return True
    except Exception as exc:
        _debug("apply_expression_lut_from_data failed", node=node, error=exc)
        return False


def _sync_hue_lut_state(node: Optional[nuke.Node]) -> None:
    if node is None:
        return

    blink = node.node("BlinkScript_OKLCHGrade")
    if blink is None:
        _debug("sync_hue_lut_state skipped: missing BlinkScript node", node=node)
        return

    expr = node.node("Expression_HueRamp")
    legacy_huecorrect = node.node("HueCorrect_HueCurves")
    ocio_in = node.node("OCIOColorSpace_IN")

    # Keep explicit input order stable in case legacy scripts lost input wiring.
    try:
        if ocio_in is not None and blink.input(0) is not ocio_in:
            blink.setInput(0, ocio_in)
    except Exception:
        pass
    try:
        if expr is not None and blink.input(1) is not expr:
            blink.setInput(1, expr)
    except Exception:
        pass

    width = 360
    try:
        if expr is not None:
            width = max(int(expr.format().width()), 2)
    except Exception:
        width = 360

    connected = False
    try:
        connected = expr is not None and blink.input(1) is expr
    except Exception:
        connected = False

    _set_blink_param_if_exists(blink, "hue_lut_width", "hue_lut_width", width)
    _set_blink_param_if_exists(blink, "hue_lut_connected", "hue_lut_connected", connected)
    _ensure_hue_curve_data(node, legacy_huecorrect)
    _apply_expression_lut_from_data(node)

    hue_curves_knob = _knob(node, "hue_curves_enable")
    curves_requested = False
    if hue_curves_knob is not None:
        try:
            curves_requested = bool(hue_curves_knob.value())
        except Exception:
            curves_requested = False

    if connected:
        # Re-assert enable state on Blink in case link expression is stale.
        _set_blink_param_if_exists(
            blink,
            "hue_curves_enable",
            "hue_curves_enable",
            curves_requested,
        )

    if not connected:
        _set_blink_param_if_exists(blink, "hue_curves_enable", "hue_curves_enable", False)
        if hue_curves_knob is not None:
            try:
                hue_curves_knob.setValue(False)
            except Exception:
                pass
        if curves_requested:
            _set_status(
                node,
                (
                    "<font color='#cc9966'><small><b>Status:</b> "
                    "Hue Curves disabled: missing internal LUT helper nodes in this instance."
                    "</small></font>"
                ),
            )
    _debug(
        f"sync_hue_lut_state width={width} connected={connected} curves_requested={curves_requested}",
        node=node,
    )


def _resolve_callback_node() -> Optional[nuke.Node]:
    try:
        node = nuke.thisNode()
    except Exception:
        node = None
    if node is not None and _knob(node, "hue_curve_data") is not None:
        return node

    # Some knobChanged invocations from floating UI arrive without thisNode.
    # Use explicit owner hint set by the floating editor/widget.
    if _CALLBACK_NODE_HINT:
        try:
            hinted = nuke.toNode(_CALLBACK_NODE_HINT)
        except Exception:
            hinted = None
        if hinted is not None and _knob(hinted, "hue_curve_data") is not None:
            return hinted
    return None


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
        _debug("sync_links: blink not ready", node=node)
        return len(_PARAM_LINKS)

    if missing:
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> Blink kernel params missing after compile: "
                f"{', '.join(missing[:6])}{'...' if len(missing) > 6 else ''}.</small></font>"
            ),
        )
        _debug(f"sync_links: missing blink params count={len(missing)}", node=node)
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

    _debug(f"sync_links done unresolved={unresolved} force_recompile={force_recompile}", node=node)
    return unresolved


def initialize_this_node() -> None:
    """onCreate entrypoint — wrapped so exceptions never crash Nuke."""
    global _in_callback
    if _in_callback:
        _debug("initialize_this_node skipped: re-entrant call")
        return
    _in_callback = True
    try:
        _debug("initialize_this_node start")
        _initialize_this_node_impl()
    except Exception as exc:
        _debug("initialize_this_node failed", error=exc)
    finally:
        _in_callback = False
        _debug("initialize_this_node end")


def _initialize_this_node_impl() -> None:
    node = nuke.thisNode()
    _check_debug_knob(node)
    _debug("initialize_impl start", node=node)
    _diag_dump("onCreate_START", node)
    _ensure_hue_lut_format()
    _apply_colorspace_defaults(node)
    unresolved = _sync_links(node, force_recompile=False)
    if unresolved:
        # One more forced pass for legacy setups where params appear after
        # first compile/reload cycle.
        unresolved = _sync_links(node, force_recompile=True)
    _sync_hue_lut_state(node)
    if unresolved:
        if "#cc6666" in _status_value(node).lower():
            return
        _set_status(
            node,
            (
                "<font color='#cc6666'><small><b>Status:</b> "
                "{} linked controls are unresolved. Open BlinkScript node and click Recompile."
                "</small></font>"
            ).format(unresolved),
        )
    _diag_dump("onCreate_END", node)
    _debug(f"initialize_impl end unresolved={unresolved}", node=node)


def handle_this_knob_changed() -> None:
    """knobChanged entrypoint — guarded against re-entrancy and throttled.

    Only knobs in ``_KNOBS_NEEDING_SYNC`` trigger the expensive sync path.
    All other knob changes (slider drags on linked params, etc.) are no-ops
    because the Link_Knob mechanism already forwards values to BlinkScript.
    """
    global _in_callback
    if _in_callback:
        _debug("handle_this_knob_changed skipped: re-entrant call")
        return

    # Filter: only react to knobs that actually need attention.
    try:
        knob = nuke.thisKnob()
        knob_name = knob.name() if knob is not None else ""
    except Exception:
        knob_name = ""

    node_for_log = _resolve_callback_node()
    if knob_name and knob_name not in _KNOBS_NEEDING_SYNC:
        _debug(f"handle_this_knob_changed ignored knob={knob_name}", node=node_for_log)
        return

    _in_callback = True
    try:
        _debug(f"handle_this_knob_changed processing knob={knob_name}", node=node_for_log)
        _handle_this_knob_changed_impl(node_for_log, knob_name=knob_name)
    except Exception as exc:
        _debug("handle_this_knob_changed failed", node=node_for_log, error=exc)
    finally:
        _in_callback = False
        _debug("handle_this_knob_changed end", node=node_for_log)


def _handle_this_knob_changed_impl(node: Optional[nuke.Node], knob_name: str = "") -> None:
    if knob_name in _LIGHTWEIGHT_SYNC_KNOBS:
        _sync_hue_lut_state(node)
        _debug(f"handle_impl lightweight_sync knob={knob_name}", node=node)
        return

    unresolved = _sync_links(node, force_recompile=False)
    if unresolved:
        _sync_links(node, force_recompile=True)
    _sync_hue_lut_state(node)
    _debug(f"handle_impl full_sync unresolved={unresolved} knob={knob_name}", node=node)
