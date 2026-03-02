"""Lightweight entrypoint for OKLCH hue widget creation.

This wrapper intentionally avoids importing the heavy Qt widget module until
needed, so we can bisect crashes at the earliest possible boundary.
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Optional

try:
    import nuke
except Exception:
    nuke = None

_WIDGET_MODE_ENV = "OKLCH_HUE_WIDGET_MODE"
_WIDGET_DEBUG_ENV = "OKLCH_HUE_WIDGET_DEBUG"
_WIDGET_DEBUG_LOG_ENV = "OKLCH_HUE_WIDGET_LOG"
_WIDGET_MODE_FILE = os.path.expanduser("~/.nuke/oklch_hue_widget_mode.txt")
_WIDGET_DEBUG_FILE = os.path.expanduser("~/.nuke/oklch_debug_on.txt")
_WIDGET_DEFAULT_LOG = "/tmp/oklch_hue_widget.log"
_WIDGET_DEBUG_ALWAYS = True


class _FallbackWidget:
    def __init__(self, reason: str = "") -> None:
        self._reason = reason

    def makeUI(self):
        _debug(f"fallback.makeUI reason={self._reason or '<none>'}")
        return None

    def updateValue(self):
        _debug(f"fallback.updateValue reason={self._reason or '<none>'}")
        return None


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _debug_enabled() -> bool:
    if _WIDGET_DEBUG_ALWAYS:
        return True
    if _is_truthy(os.environ.get(_WIDGET_DEBUG_ENV, "")):
        return True
    try:
        return os.path.isfile(_WIDGET_DEBUG_FILE)
    except Exception:
        return False


def _debug_log_path() -> str:
    env_path = os.environ.get(_WIDGET_DEBUG_LOG_ENV, "").strip()
    if env_path:
        return env_path
    return _WIDGET_DEFAULT_LOG


def _debug(message: str, *, error: Optional[Exception] = None) -> None:
    if not _debug_enabled():
        return
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] pid={os.getpid()} mode={_widget_mode()} {message}"
    if error is not None:
        line += f" error={error!r}"

    try:
        if nuke is not None and hasattr(nuke, "tprint"):
            nuke.tprint(f"[OKLCH HueWidget Entry] {line}")
        else:
            print(f"[OKLCH HueWidget Entry] {line}")
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


def _mode_from_file() -> str:
    try:
        if os.path.isfile(_WIDGET_MODE_FILE):
            with open(_WIDGET_MODE_FILE, "r", encoding="utf-8") as handle:
                return handle.read().strip().lower()
    except Exception:
        return ""
    return ""


def _widget_mode() -> str:
    raw = os.environ.get(_WIDGET_MODE_ENV, "").strip().lower()
    if not raw:
        raw = _mode_from_file()
    if not raw:
        raw = "full"

    aliases = {
        "interactive": "full",
        "minimal": "probe",
        "disabled": "off",
    }
    mode = aliases.get(raw, raw)
    if mode not in ("off", "bare", "probe", "paint", "readonly", "full"):
        return "full"
    return mode


def _build_bare_widget():
    """Return raw QWidget instance wrapped for PyCustom (no subclass behavior)."""
    qt_err: Optional[Exception] = None
    try:
        from PySide6.QtWidgets import QWidget  # type: ignore[import-untyped]
    except Exception as exc:
        qt_err = exc
        try:
            from PySide2.QtWidgets import QWidget  # type: ignore[import-untyped,no-redef]
        except Exception as exc2:
            _debug("bare mode Qt import failed", error=exc2)
            if qt_err is not None:
                _debug("bare mode first import error", error=qt_err)
            return _FallbackWidget("bare_qt_import_failed")

    class _BareWidget:
        def __init__(self) -> None:
            self._w = QWidget()
            self._w.setMinimumHeight(24)

        def makeUI(self):
            _debug("bare.makeUI")
            return self._w

        def updateValue(self):
            _debug("bare.updateValue")
            return None

    return _BareWidget()


def _build_probe_widget(node):
    """Return minimal QWidget subclass (no paint/input/data)."""
    qt_err: Optional[Exception] = None
    try:
        from PySide6.QtWidgets import QWidget  # type: ignore[import-untyped]
    except Exception as exc:
        qt_err = exc
        try:
            from PySide2.QtWidgets import QWidget  # type: ignore[import-untyped,no-redef]
        except Exception as exc2:
            _debug("probe mode Qt import failed", error=exc2)
            if qt_err is not None:
                _debug("probe mode first import error", error=qt_err)
            return _FallbackWidget("probe_qt_import_failed")

    class _ProbeWidget(QWidget):
        def __init__(self, _node) -> None:
            super().__init__()
            self._node = _node
            self.setMinimumHeight(36)
            _debug("probe.init")

        def makeUI(self):
            _debug("probe.makeUI")
            return self

        def updateValue(self):
            _debug("probe.updateValue")
            return None

    try:
        return _ProbeWidget(node)
    except Exception as exc:
        _debug("probe widget construction failed", error=exc)
        return _FallbackWidget("probe_construction_failed")


def create_widget(node):
    """Entrypoint called by PyCustom_Knob command string."""
    mode = _widget_mode()
    _debug(f"create_widget start mode={mode}")

    if _is_truthy(os.environ.get("OKLCH_DISABLE_HUE_CURVE_WIDGET", "")):
        return _FallbackWidget("OKLCH_DISABLE_HUE_CURVE_WIDGET")

    if nuke is not None:
        try:
            if not nuke.GUI():
                return _FallbackWidget("non_gui_session")
        except Exception as exc:
            _debug("nuke.GUI check failed", error=exc)

    if mode == "off":
        return _FallbackWidget(f"{_WIDGET_MODE_ENV}=off")

    if mode == "bare":
        return _build_bare_widget()

    if mode == "probe":
        return _build_probe_widget(node)

    try:
        import hue_curve_widget_impl as _impl
    except Exception as exc:
        _debug("import hue_curve_widget_impl failed", error=exc)
        return _FallbackWidget("impl_import_failed")

    try:
        return _impl.create_widget(node)
    except Exception as exc:
        _debug("impl.create_widget failed", error=exc)
        return _FallbackWidget("impl_create_widget_failed")


def create_probe_widget(node):
    """Hard-wired minimal PyCustom probe for studio diagnostic runs."""
    _debug("create_probe_widget start")
    if nuke is not None:
        try:
            if not nuke.GUI():
                return _FallbackWidget("non_gui_session")
        except Exception as exc:
            _debug("create_probe_widget nuke.GUI check failed", error=exc)
    return _build_probe_widget(node)


def __getattr__(name: str):
    """Back-compat: allow direct imports from the old module surface."""
    if name in {"HueCurveWidget"}:
        import hue_curve_widget_impl as _impl

        return getattr(_impl, name)
    raise AttributeError(name)


_debug("module_loaded")
