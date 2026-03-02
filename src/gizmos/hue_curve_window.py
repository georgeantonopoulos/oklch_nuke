"""Floating hue-curve editor for OKLCH_Grade.

This avoids PyCustom inline embedding, which crashes on some Linux/Nuke16
studio stacks, by launching a standalone Qt window on demand.
"""

from __future__ import annotations

from typing import Dict, Optional

import nuke

try:
    from PySide6.QtCore import Qt  # type: ignore[import-untyped]
    from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout  # type: ignore[import-untyped]
    _HAS_QT = True
except Exception:
    try:
        from PySide2.QtCore import Qt  # type: ignore[import-untyped,no-redef]
        from PySide2.QtWidgets import QDialog, QLabel, QVBoxLayout  # type: ignore[import-untyped,no-redef]
        _HAS_QT = True
    except Exception:
        _HAS_QT = False

_WINDOWS: Dict[str, QDialog] = {}


def _node_key(node: Optional[nuke.Node]) -> str:
    if node is None:
        return ""
    try:
        return str(node.fullName())
    except Exception:
        try:
            return str(node.name())
        except Exception:
            return ""


class HueCurveEditorWindow(QDialog):
    def __init__(self, node: nuke.Node) -> None:
        super().__init__(None)
        self._node = node

        try:
            title_name = str(node.name())
        except Exception:
            title_name = "OKLCH_Grade"

        self.setWindowTitle(f"OKLCH Hue Curve Editor - {title_name}")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(760, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QLabel(
            "Floating editor mode (Linux-safe): edits are written to "
            "hue_curve_data and HueCorrect sat-curve in the node graph."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        import hue_curve_widget_impl as _impl

        self._curve_widget = _impl.HueCurveWidget(
            node,
            allow_edit=True,
            push_to_huecorrect=True,
            show_reset_button=True,
        )
        layout.addWidget(self._curve_widget, 1)

    def showEvent(self, event):  # type: ignore[override]
        try:
            self._curve_widget.updateValue()
        except Exception:
            pass
        return super().showEvent(event)

    def closeEvent(self, event):  # type: ignore[override]
        key = _node_key(self._node)
        if key and _WINDOWS.get(key) is self:
            _WINDOWS.pop(key, None)
        return super().closeEvent(event)


def open_for_node(node: Optional[nuke.Node]) -> None:
    """Open or raise a floating editor for *node*."""
    if node is None:
        try:
            node = nuke.thisNode()
        except Exception:
            node = None

    if node is None:
        try:
            node = nuke.selectedNode()
        except Exception:
            node = None

    if node is None:
        nuke.message("No node selected. Select an OKLCH_Grade node first.")
        return

    if not _HAS_QT:
        nuke.message("Qt bindings are unavailable in this Nuke session.")
        return

    try:
        if node.Class() != "Group":
            # Keep soft guard (gizmo class can vary between Group/Gizmo wrappers).
            pass
    except Exception:
        pass

    key = _node_key(node)
    existing = _WINDOWS.get(key)
    if existing is not None:
        try:
            try:
                existing._curve_widget.updateValue()  # type: ignore[attr-defined]
            except Exception:
                pass
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        except Exception:
            _WINDOWS.pop(key, None)

    try:
        win = HueCurveEditorWindow(node)
    except Exception as exc:
        nuke.message(f"Failed to open floating hue editor:\n{exc}")
        return

    if key:
        _WINDOWS[key] = win
    win.show()
    win.raise_()
    win.activateWindow()
