"""Custom Qt hue-curve widget for OKLCH_Grade gizmo.

Supports both PySide6 (Nuke 16+) and PySide2 (Nuke 14-15).
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

import hue_curve_data as _hcd

try:
    import nuke
except Exception:  # pragma: no cover - exercised in Nuke host only
    nuke = None

# Nuke 16+ ships PySide6; Nuke 14/15 ship PySide2.
_HAS_QT = False
try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal  # type: ignore[import-untyped]
    from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen  # type: ignore[import-untyped]
    from PySide6.QtWidgets import (  # type: ignore[import-untyped]
        QHBoxLayout,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except Exception:
    try:
        from PySide2.QtCore import QPointF, QRectF, QSize, Qt, Signal  # type: ignore[import-untyped,no-redef]
        from PySide2.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen  # type: ignore[import-untyped,no-redef]
        from PySide2.QtWidgets import (  # type: ignore[import-untyped,no-redef]
            QHBoxLayout,
            QPushButton,
            QSizePolicy,
            QVBoxLayout,
            QWidget,
        )
        _HAS_QT = True
    except Exception:  # pragma: no cover - headless sessions
        pass


_POINT_RADIUS = 5.0
_HIT_RADIUS = 9.0

# Approximate OKLCH hue sweep rendered in display-space RGB.
_RAINBOW_STOPS = (
    (0.00, "#ff4d4d"),
    (0.08, "#ff7f4d"),
    (0.17, "#ffbf4d"),
    (0.25, "#d4d84a"),
    (0.33, "#7ccf4a"),
    (0.42, "#4bcf86"),
    (0.50, "#47c8d8"),
    (0.58, "#4b9de6"),
    (0.67, "#5f79ef"),
    (0.75, "#8e67ef"),
    (0.83, "#bf62e8"),
    (0.92, "#e55eb8"),
    (1.00, "#ff4d4d"),
)


class _FallbackWidget:
    """No-op object returned in non-GUI sessions."""

    def __init__(self, node):
        self._node = node

    def makeUI(self):  # pragma: no cover - host integration only
        if _HAS_QT:
            try:
                widget = QWidget()
                widget.setMinimumHeight(2)
                return widget
            except Exception:
                return None
        return None

    def updateValue(self):  # pragma: no cover - host integration only
        return None


if _HAS_QT:

    class _HueCurveCanvas(QWidget):
        pointsChanged = Signal(object)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._points: list[tuple[float, float]] = list(_hcd._DEFAULT_POINTS)
            self._drag_index: Optional[int] = None
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setMinimumHeight(200)
            self.setMouseTracking(True)

        def set_points(self, points: Iterable[Iterable[float]]) -> None:
            self._points = _hcd.normalize_points(points)
            self.update()

        def points(self) -> list[tuple[float, float]]:
            return list(self._points)

        def sizeHint(self) -> QSize:
            return QSize(420, 220)

        def _plot_rect(self) -> QRectF:
            margin_l = 48.0
            margin_r = 14.0
            margin_t = 14.0
            margin_b = 24.0
            width = max(10.0, float(self.width()) - margin_l - margin_r)
            height = max(10.0, float(self.height()) - margin_t - margin_b)
            return QRectF(margin_l, margin_t, width, height)

        def _to_canvas(self, x: float, y: float) -> QPointF:
            plot = self._plot_rect()
            px = plot.left() + (_hcd.clamp(x, 0.0, 1.0) * plot.width())
            py = plot.top() + ((2.0 - _hcd.clamp(y, 0.0, 2.0)) / 2.0) * plot.height()
            return QPointF(px, py)

        def _from_canvas(self, point: QPointF) -> tuple[float, float]:
            plot = self._plot_rect()
            x = (point.x() - plot.left()) / max(plot.width(), 1.0)
            y = 2.0 - 2.0 * ((point.y() - plot.top()) / max(plot.height(), 1.0))
            return (_hcd.clamp(x, 0.0, 1.0), _hcd.clamp(y, 0.0, 2.0))

        def _hit_test(self, point: QPointF) -> Optional[int]:
            for idx, (x, y) in enumerate(self._points):
                control = self._to_canvas(x, y)
                dx = control.x() - point.x()
                dy = control.y() - point.y()
                if (dx * dx + dy * dy) <= (_HIT_RADIUS * _HIT_RADIUS):
                    return idx
            return None

        def _event_pos(self, event) -> QPointF:
            try:
                return event.localPos()
            except Exception:
                pass
            try:
                return event.posF()
            except Exception:
                pass
            point = event.pos()
            return QPointF(point)

        def _emit_changed(self) -> None:
            self._points = _hcd.normalize_points(self._points)
            self.pointsChanged.emit(self.points())
            self.update()

        def _move_point(self, index: int, x: float, y: float) -> None:
            """Mutate a single point. Caller must call ``_emit_changed()`` after."""
            pts = list(self._points)
            y = _hcd.clamp(y, 0.0, 2.0)
            if index in (0, len(pts) - 1):
                y_wrap = y
                pts[0] = (0.0, y_wrap)
                pts[-1] = (1.0, y_wrap)
                self._points = pts
                return

            left_x = pts[index - 1][0] + 1e-4
            right_x = pts[index + 1][0] - 1e-4
            x = _hcd.clamp(x, left_x, right_x)
            pts[index] = (x, y)
            self._points = pts

        def paintEvent(self, _event) -> None:  # pragma: no cover - GUI behavior
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)

            plot = self._plot_rect()
            painter.fillRect(self.rect(), QColor("#202326"))

            grad = QLinearGradient(plot.left(), plot.top(), plot.right(), plot.top())
            for pos, color_hex in _RAINBOW_STOPS:
                grad.setColorAt(pos, QColor(color_hex))
            painter.fillRect(plot, grad)

            painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
            for degree in (0, 60, 120, 180, 240, 300, 360):
                x = plot.left() + (degree / 360.0) * plot.width()
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

            y_labels = ((0.0, "-180"), (0.5, "-90"), (1.0, "0"), (1.5, "+90"), (2.0, "+180"))
            for value, label in y_labels:
                y = self._to_canvas(0.0, value).y()
                pen = QPen(QColor(255, 255, 255, 60), 1.0)
                if abs(value - 1.0) < _hcd._EPSILON:
                    pen = QPen(QColor(255, 255, 255, 120), 1.2, Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                painter.setPen(QPen(QColor("#d9d9d9"), 1.0))
                painter.drawText(QPointF(8.0, y + 4.0), label)

            spline = QPainterPath()
            samples = max(int(plot.width()), 180)
            for idx in range(samples + 1):
                x = idx / float(samples)
                y = _hcd.clamp(_hcd.catmull_rom_y(self._points, x), 0.0, 2.0)
                p = self._to_canvas(x, y)
                if idx == 0:
                    spline.moveTo(p)
                else:
                    spline.lineTo(p)

            painter.setPen(QPen(QColor("#121416"), 4.0))
            painter.drawPath(spline)
            painter.setPen(QPen(QColor("#f5f7ff"), 2.0))
            painter.drawPath(spline)

            for x, y in self._points:
                p = self._to_canvas(x, y)
                painter.setBrush(QColor("#121416"))
                painter.setPen(QPen(QColor("#f5f7ff"), 2.0))
                painter.drawEllipse(p, _POINT_RADIUS + 1.0, _POINT_RADIUS + 1.0)
                painter.setBrush(QColor("#75c7ff"))
                painter.drawEllipse(p, _POINT_RADIUS - 1.5, _POINT_RADIUS - 1.5)

            painter.setPen(QPen(QColor("#d9d9d9"), 1.0))
            painter.drawText(QPointF(plot.left(), float(self.height()) - 6.0), "0°")
            painter.drawText(QPointF(plot.right() - 30.0, float(self.height()) - 6.0), "360°")

        def mousePressEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            if event.button() not in (Qt.LeftButton, Qt.RightButton):
                return

            pos = self._event_pos(event)
            idx = self._hit_test(pos)
            if event.button() == Qt.RightButton:
                if idx is not None and idx not in (0, len(self._points) - 1):
                    pts = list(self._points)
                    pts.pop(idx)
                    self._points = pts
                    self._emit_changed()
                return

            if idx is None:
                x, y = self._from_canvas(pos)
                pts = list(self._points)
                insert_idx = 1
                while insert_idx < len(pts) and pts[insert_idx][0] < x:
                    insert_idx += 1
                pts.insert(insert_idx, (x, y))
                self._points = _hcd.normalize_points(pts)
                self._drag_index = self._hit_test(pos)
                self._emit_changed()
                return

            self._drag_index = idx

        def mouseMoveEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            if self._drag_index is None:
                return
            x, y = self._from_canvas(self._event_pos(event))
            self._move_point(self._drag_index, x, y)
            self._emit_changed()

        def mouseReleaseEvent(self, _event) -> None:  # pragma: no cover - GUI behavior
            self._drag_index = None

        def mouseDoubleClickEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            if event.button() != Qt.LeftButton:
                return
            idx = self._hit_test(self._event_pos(event))
            if idx is None:
                return
            x = self._points[idx][0]
            self._move_point(idx, x, 1.0)
            self._emit_changed()

    class HueCurveWidget:
        """PyCustom wrapper object that builds/returns a QWidget in makeUI()."""

        def __init__(self, node) -> None:
            self._node = node
            self._points: list[tuple[float, float]] = list(_hcd._DEFAULT_POINTS)
            self._container: Optional[QWidget] = None
            self._canvas: Optional[_HueCurveCanvas] = None
            self._reset: Optional[QPushButton] = None
            self._is_updating = False

        def makeUI(self):  # pragma: no cover - host integration only
            self._container = QWidget()
            self._container.setMinimumHeight(220)
            self._container.setToolTip(
                "Left-click: add/drag point | Right-click: remove point | "
                "Double-click: reset to neutral (Y=1.0)"
            )

            root = QVBoxLayout(self._container)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(6)

            self._canvas = _HueCurveCanvas(self._container)
            self._canvas.pointsChanged.connect(self._on_curve_changed)
            root.addWidget(self._canvas)

            buttons = QHBoxLayout()
            buttons.addStretch(1)
            self._reset = QPushButton("Reset", self._container)
            self._reset.clicked.connect(self._reset_curve)
            buttons.addWidget(self._reset)
            root.addLayout(buttons)

            self.updateValue()
            return self._container

        def updateValue(self):  # pragma: no cover - host integration only
            if self._canvas is None:
                return
            self._is_updating = True
            try:
                # Read-only: restore widget state from knob. Do NOT write back
                # here — updateValue() can be called on panel opens and should
                # not dirty scripts or trigger extra cooks.
                self._points = self._load_points_from_knob()
                self._canvas.set_points(self._points)
            finally:
                self._is_updating = False

        def _curve_data_knob(self):
            if self._node is None:
                return None
            try:
                return self._node.knob("hue_curve_data")
            except Exception:
                return None

        def _load_points_from_knob(self) -> list[tuple[float, float]]:
            knob = self._curve_data_knob()
            raw = ""
            if knob is not None:
                try:
                    raw = str(knob.value() or "")
                except Exception:
                    raw = ""
            if raw.strip():
                try:
                    import json
                    data = json.loads(raw)
                    return _hcd.normalize_points(data)
                except Exception:
                    pass

            # Legacy fallback: read existing HueCorrect sat curve when JSON has
            # not been populated yet.
            try:
                hc = self._node.node("HueCorrect_HueCurves") if self._node is not None else None
                hue_knob = hc.knob("hue") if hc is not None else None
                if hue_knob is not None:
                    legacy = _hcd.parse_hue_script_points(hue_knob.toScript())
                    if legacy is not None and len(legacy) >= 2:
                        return legacy
            except Exception:
                pass
            return list(_hcd._DEFAULT_POINTS)

        def _save_points_to_knob(self) -> None:
            knob = self._curve_data_knob()
            if knob is None:
                return
            try:
                knob.setValue(_hcd.points_to_json(self._points))
            except Exception:
                pass

        def _push_curve_to_huecorrect(self) -> None:
            if self._node is None:
                return
            try:
                hc = self._node.node("HueCorrect_HueCurves")
                hue_knob = hc.knob("hue") if hc is not None else None
                if hue_knob is None:
                    return
                hue_knob.fromScript(_hcd.points_to_hue_script(self._points))
            except Exception as exc:
                # Surface the error on the gizmo status knob so the user knows
                # the HueCorrect backend is out of sync.
                try:
                    status = self._node.knob("status_text")
                    if status is not None:
                        msg = str(exc).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        status.setValue(
                            "<font color='#cc6666'><small><b>Status:</b> "
                            f"HueCorrect curve update failed: {msg}</small></font>"
                        )
                except Exception:
                    pass

        def _on_curve_changed(self, points: Iterable[Iterable[float]]) -> None:
            if self._is_updating:
                return
            self._points = _hcd.normalize_points(points)
            self._save_points_to_knob()
            self._push_curve_to_huecorrect()

        def _reset_curve(self) -> None:
            self._points = list(_hcd._DEFAULT_POINTS)
            if self._canvas is not None:
                self._canvas.set_points(self._points)
            self._save_points_to_knob()
            self._push_curve_to_huecorrect()


def create_widget(node):
    """Factory entrypoint used by PyCustom_Knob command strings."""
    if os.environ.get("OKLCH_DISABLE_HUE_CURVE_WIDGET", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        return _FallbackWidget(node)

    if not _HAS_QT:
        return _FallbackWidget(node)

    if nuke is not None:
        try:
            if not nuke.GUI():
                return _FallbackWidget(node)
        except Exception:
            pass

    try:
        return HueCurveWidget(node)
    except Exception:
        return _FallbackWidget(node)
