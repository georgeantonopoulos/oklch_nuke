"""Floating hue-curve editor for OKLCH_Grade.

This avoids PyCustom inline embedding, which crashes on some Linux/Nuke16
studio stacks, by launching a standalone Qt window on demand.
"""

from __future__ import annotations

from typing import Dict, Optional

import nuke

try:
    from PySide6.QtCore import Qt  # type: ignore[import-untyped]
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap  # type: ignore[import-untyped]
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout  # type: ignore[import-untyped]
    _HAS_QT = True
except Exception:
    try:
        from PySide2.QtCore import Qt  # type: ignore[import-untyped,no-redef]
        from PySide2.QtGui import QColor, QIcon, QPainter, QPen, QPixmap  # type: ignore[import-untyped,no-redef]
        from PySide2.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout  # type: ignore[import-untyped,no-redef]
        _HAS_QT = True
    except Exception:
        _HAS_QT = False

try:
    import hue_curve_data as _hcd
except Exception:
    _hcd = None  # type: ignore[assignment]

_WINDOWS: Dict[str, QDialog] = {}

# Global picker state: at most one window is actively picking at a time.
_active_picker: Optional["HueCurveEditorWindow"] = None


def _register_picker(win: "HueCurveEditorWindow") -> None:
    global _active_picker
    _active_picker = win


def _unregister_picker(win: "HueCurveEditorWindow") -> None:
    global _active_picker
    if _active_picker is win:
        _active_picker = None
        try:
            nuke.removeKnobChanged(
                _global_pick_handler, nodeClass="Viewer"
            )
        except Exception:
            pass


def _global_pick_handler() -> None:
    """Global knobChanged callback for Viewer nodes during picking."""
    try:
        knob = nuke.thisKnob()
        if knob is None or knob.name() != "colour_sample_bbox":
            return
        if _active_picker is not None:
            _active_picker._handle_viewer_sample()
    except Exception:
        pass


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

        self.setWindowTitle(f"Hue Shift Curve - {title_name}")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(760, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info = QLabel(
            "Drag points to shift hues across the colour wheel. "
            "The dashed centre line is neutral (no shift)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Eyedropper toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        self._pick_btn = QPushButton()
        self._pick_btn.setToolTip(
            "Click this button, then Ctrl-click a pixel in the Nuke viewer "
            "to add a control point at that pixel's hue."
        )
        self._pick_btn.setCheckable(True)
        self._pick_btn.clicked.connect(self._toggle_pick_mode)
        # Draw an eyedropper icon on a small pixmap
        self._pick_btn.setFixedSize(28, 28)
        self._set_pick_icon(checked=False)
        toolbar.addWidget(self._pick_btn)
        self._pick_status = QLabel("")
        toolbar.addWidget(self._pick_status)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._picking = False

        import hue_curve_widget_impl as _impl

        self._curve_widget = _impl.HueCurveWidget(
            node,
            allow_edit=True,
            push_runtime_lut=True,
            show_reset_button=True,
        )
        layout.addWidget(self._curve_widget, 1)

    # ---- Interactive hue picker ----

    def _toggle_pick_mode(self) -> None:
        """Toggle interactive picking: install/remove a Viewer knobChanged callback."""
        if self._picking:
            self._stop_picking()
        else:
            self._start_picking()

    def _start_picking(self) -> None:
        if self._node is None:
            nuke.message("No node attached to this editor.")
            self._pick_btn.setChecked(False)
            return
        if _hcd is None or not hasattr(_hcd, "linsrgb_to_hue_normalized"):
            nuke.message("hue_curve_data module missing OKLCH conversion support.")
            self._pick_btn.setChecked(False)
            return
        self._picking = True
        self._pick_btn.setChecked(True)
        self._pick_btn.setText("Ctrl+Click on Viewer...")
        self._pick_status.setText("")
        # Register a global callback watching Viewer knob changes.
        # We store a reference to the bound method so we can remove it later.
        nuke.addKnobChanged(
            _global_pick_handler, nodeClass="Viewer"
        )
        _register_picker(self)

    def _stop_picking(self) -> None:
        self._picking = False
        self._pick_btn.setChecked(False)
        self._pick_btn.setText("Pick Hue from Viewer")
        _unregister_picker(self)

    def _handle_viewer_sample(self) -> None:
        """Called when colour_sample_bbox changes while picking is active."""
        if not self._picking:
            return
        try:
            viewer_node = nuke.thisNode()
            bbox_knob = viewer_node.knob("colour_sample_bbox")
            if bbox_knob is None:
                return
            bbox = bbox_knob.value()

            # colour_sample_bbox is in normalised (-1..1) space.
            # Convert to pixel coordinates using the gizmo's input format.
            inp = self._node.input(0)
            if inp is None:
                self._pick_status.setText("No input connected to node.")
                return
            w = float(inp.width())
            h = float(inp.height())
            aspect = w / max(h, 1.0)

            # Centre of the sample bbox
            nx = (bbox[0] + bbox[2]) / 2.0
            ny = (bbox[1] + bbox[3]) / 2.0
            px = (nx * 0.5 + 0.5) * w
            py = ((ny * 0.5) + (0.5 / aspect)) * aspect * h

            # Sample linear-sRGB from OCIOColorSpace_IN output
            ocio_in = self._node.node("OCIOColorSpace_IN")
            if ocio_in is None:
                self._pick_status.setText("OCIOColorSpace_IN missing.")
                return
            r = ocio_in.sample("red",   px, py)
            g = ocio_in.sample("green", px, py)
            b = ocio_in.sample("blue",  px, py)

            hue_x, chroma = _hcd.linsrgb_to_hue_normalized(r, g, b)
            if chroma < _hcd._CHROMA_FLOOR:
                self._pick_status.setText(
                    "Near-neutral pixel — hue undefined. Try a more saturated area."
                )
                return

            hue_deg = hue_x * 360.0
            self._curve_widget.add_point_at_hue(hue_x, 1.0)
            self._pick_status.setText(f"Added point at {hue_deg:.0f}\u00b0")
            try:
                nuke.tprint(
                    f"[OKLCH HuePick] lin-sRGB ({r:.4f}, {g:.4f}, {b:.4f}) "
                    f"-> hue {hue_deg:.1f}\u00b0, chroma={chroma:.6f}"
                )
            except Exception:
                pass
        except Exception as exc:
            self._pick_status.setText(f"Pick failed: {exc}")

        # Exit picking mode after one successful pick.
        self._stop_picking()

    def showEvent(self, event):  # type: ignore[override]
        try:
            self._curve_widget.updateValue()
        except Exception:
            pass
        return super().showEvent(event)

    def closeEvent(self, event):  # type: ignore[override]
        if self._picking:
            self._stop_picking()
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
