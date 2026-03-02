"""Floating hue-curve editor for OKLCH_Grade.

This avoids PyCustom inline embedding, which crashes on some Linux/Nuke16
studio stacks, by launching a standalone Qt window on demand.
"""

from __future__ import annotations

from typing import Dict, Optional

import nuke

try:
    from PySide6.QtCore import Qt  # type: ignore[import-untyped]
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout  # type: ignore[import-untyped]
    _HAS_QT = True
except Exception:
    try:
        from PySide2.QtCore import Qt  # type: ignore[import-untyped,no-redef]
        from PySide2.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout  # type: ignore[import-untyped,no-redef]
        _HAS_QT = True
    except Exception:
        _HAS_QT = False

try:
    import hue_curve_data as _hcd
except Exception:
    _hcd = None  # type: ignore[assignment]

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
        self._pick_btn = QPushButton("Pick Hue from Viewer")
        self._pick_btn.setToolTip(
            "Ctrl-click a pixel in the Nuke viewer, then press this button "
            "to add a control point at that pixel's hue."
        )
        self._pick_btn.clicked.connect(self._pick_hue_from_viewer)
        toolbar.addWidget(self._pick_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        import hue_curve_widget_impl as _impl

        self._curve_widget = _impl.HueCurveWidget(
            node,
            allow_edit=True,
            push_runtime_lut=True,
            show_reset_button=True,
        )
        layout.addWidget(self._curve_widget, 1)

    def _pick_hue_from_viewer(self) -> None:
        """Sample viewer Ctrl-click position, convert to OKLCH hue, add point."""
        if self._node is None:
            nuke.message("No node attached to this editor.")
            return
        if _hcd is None or not hasattr(_hcd, "linsrgb_to_hue_normalized"):
            nuke.message("hue_curve_data module missing OKLCH conversion support.")
            return

        # Get sample position from the viewer's last Ctrl-click
        viewer = nuke.activeViewer()
        if viewer is None:
            nuke.message(
                "No active viewer.\n\n"
                "Ctrl-click on a pixel in the viewer first, then press Pick Hue."
            )
            return
        viewer_node = viewer.node()
        if viewer_node is None:
            nuke.message("Cannot access viewer node.")
            return
        try:
            bbox_knob = viewer_node.knob("colour_sample_bbox")
            if bbox_knob is None:
                nuke.message(
                    "Viewer has no colour_sample_bbox.\n\n"
                    "Ctrl-click on a pixel in the viewer first."
                )
                return
            bbox = bbox_knob.value()
            sample_x = (bbox[0] + bbox[2]) / 2.0
            sample_y = (bbox[1] + bbox[3]) / 2.0
        except Exception as exc:
            nuke.message(f"Failed to read viewer sample position:\n{exc}")
            return

        # Sample linear-sRGB from OCIOColorSpace_IN output
        ocio_in = self._node.node("OCIOColorSpace_IN")
        if ocio_in is None:
            nuke.message(
                "Cannot find OCIOColorSpace_IN inside the gizmo.\n"
                "The gizmo internals may be damaged."
            )
            return
        try:
            r = ocio_in.sample("red",   sample_x, sample_y)
            g = ocio_in.sample("green", sample_x, sample_y)
            b = ocio_in.sample("blue",  sample_x, sample_y)
        except Exception as exc:
            nuke.message(f"Failed to sample pixel:\n{exc}")
            return

        # Convert to OKLCH hue
        hue_x, chroma = _hcd.linsrgb_to_hue_normalized(r, g, b)
        if chroma < _hcd._CHROMA_FLOOR:
            nuke.message(
                "The sampled colour is near-neutral (very low chroma).\n\n"
                "Hue is undefined for achromatic colours. "
                "Try sampling a more saturated pixel."
            )
            return

        hue_deg = hue_x * 360.0
        self._curve_widget.add_point_at_hue(hue_x, 1.0)
        try:
            nuke.tprint(
                f"[OKLCH HuePick] lin-sRGB ({r:.4f}, {g:.4f}, {b:.4f}) "
                f"-> hue {hue_deg:.1f} deg, chroma={chroma:.6f}"
            )
        except Exception:
            pass

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
