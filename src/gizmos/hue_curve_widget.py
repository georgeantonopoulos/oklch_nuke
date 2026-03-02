"""Custom Qt hue-curve widget for OKLCH_Grade gizmo.

Supports both PySide6 (Nuke 16+) and PySide2 (Nuke 14-15).
All Qt operations are wrapped defensively so that a failure degrades to a
no-op fallback widget instead of crashing Nuke.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

try:
    import hue_curve_data as _hcd
except Exception:
    _hcd = None  # type: ignore[assignment]

try:
    import nuke
except Exception:  # pragma: no cover - exercised in Nuke host only
    nuke = None

# ---------------------------------------------------------------------------
# Qt import with PySide6 / PySide2 compat
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# PySide6 scoped-enum compatibility helpers
# ---------------------------------------------------------------------------
# PySide6 (Qt 6) moved enums into scoped sub-namespaces.  Some Linux builds
# disable the backwards-compat shim, causing attribute access like
# ``Qt.LeftButton`` to segfault or raise AttributeError.  Resolve once at
# import time so the hot paths (paint, mouse) never fail.

def _resolve_enum(parent, *candidates):
    """Return the first attribute that resolves, or the last candidate name."""
    for dotpath in candidates:
        obj = parent
        try:
            for part in dotpath.split("."):
                obj = getattr(obj, part)
            return obj
        except (AttributeError, TypeError):
            continue
    return None


if _HAS_QT:
    _LeftButton = _resolve_enum(Qt, "MouseButton.LeftButton", "LeftButton")
    _RightButton = _resolve_enum(Qt, "MouseButton.RightButton", "RightButton")
    _DashLine = _resolve_enum(Qt, "PenStyle.DashLine", "DashLine")
    _Antialiasing = _resolve_enum(QPainter, "RenderHint.Antialiasing", "Antialiasing")
    _SizeExpanding = _resolve_enum(QSizePolicy, "Policy.Expanding", "Expanding")


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

# Fallback defaults if _hcd failed to import.
_DEFAULT_POINTS_FALLBACK = ((0.0, 1.0), (1.0, 1.0))


def _default_points():
    if _hcd is not None:
        return list(_hcd._DEFAULT_POINTS)
    return list(_DEFAULT_POINTS_FALLBACK)


def _safe_clamp(value, lo, hi):
    if _hcd is not None:
        return _hcd.clamp(value, lo, hi)
    return max(lo, min(hi, value))


def _safe_normalize(points):
    if _hcd is not None:
        return _hcd.normalize_points(points)
    # Minimal inline fallback — should never be reached in practice.
    pts = []
    for pair in (points or []):
        try:
            x, y = pair
            pts.append((max(0.0, min(1.0, float(x))), max(0.0, min(2.0, float(y)))))
        except Exception:
            continue
    if len(pts) < 2:
        return list(_DEFAULT_POINTS_FALLBACK)
    pts.sort(key=lambda p: p[0])
    pts[0] = (0.0, pts[0][1])
    pts[-1] = (1.0, pts[-1][1])
    return pts


def _safe_catmull_rom_y(points, x):
    if _hcd is not None:
        return _hcd.catmull_rom_y(points, x)
    # Linear interpolation fallback.
    if not points:
        return 1.0
    for i in range(len(points) - 1):
        if points[i][0] <= x <= points[i + 1][0]:
            dx = points[i + 1][0] - points[i][0]
            if dx < 1e-9:
                return points[i][1]
            t = (x - points[i][0]) / dx
            return points[i][1] + t * (points[i + 1][1] - points[i][1])
    return points[-1][1]


# ---------------------------------------------------------------------------
# Fallback widget (always defined, used when Qt is unavailable or broken)
# ---------------------------------------------------------------------------

class _FallbackWidget:
    """No-op object returned in non-GUI sessions or on widget init failure."""

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


# ---------------------------------------------------------------------------
# Qt widgets (only defined when Qt is importable)
# ---------------------------------------------------------------------------

if _HAS_QT:

    class _HueCurveCanvas(QWidget):
        pointsChanged = Signal(object)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._points: list[tuple[float, float]] = _default_points()
            self._drag_index: Optional[int] = None
            try:
                if _SizeExpanding is not None:
                    self.setSizePolicy(_SizeExpanding, _SizeExpanding)
            except Exception:
                pass
            self.setMinimumHeight(200)
            self.setMouseTracking(True)

        def set_points(self, points: Iterable[Iterable[float]]) -> None:
            self._points = _safe_normalize(points)
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
            px = plot.left() + (_safe_clamp(x, 0.0, 1.0) * plot.width())
            py = plot.top() + ((2.0 - _safe_clamp(y, 0.0, 2.0)) / 2.0) * plot.height()
            return QPointF(px, py)

        def _from_canvas(self, point: QPointF) -> tuple[float, float]:
            plot = self._plot_rect()
            x = (point.x() - plot.left()) / max(plot.width(), 1.0)
            y = 2.0 - 2.0 * ((point.y() - plot.top()) / max(plot.height(), 1.0))
            return (_safe_clamp(x, 0.0, 1.0), _safe_clamp(y, 0.0, 2.0))

        def _hit_test(self, point: QPointF) -> Optional[int]:
            for idx, (x, y) in enumerate(self._points):
                control = self._to_canvas(x, y)
                dx = control.x() - point.x()
                dy = control.y() - point.y()
                if (dx * dx + dy * dy) <= (_HIT_RADIUS * _HIT_RADIUS):
                    return idx
            return None

        def _event_pos(self, event) -> QPointF:
            """Extract local position from mouse event, Qt5 and Qt6 safe."""
            # Qt6: event.position() returns QPointF directly
            try:
                pos = event.position()
                if isinstance(pos, QPointF):
                    return pos
                return QPointF(pos)
            except (AttributeError, TypeError):
                pass
            # Qt5: event.localPos()
            try:
                return event.localPos()
            except (AttributeError, TypeError):
                pass
            # Qt5 older: event.posF()
            try:
                return event.posF()
            except (AttributeError, TypeError):
                pass
            # Last resort: event.pos() (returns QPoint, not QPointF)
            try:
                point = event.pos()
                return QPointF(point)
            except Exception:
                return QPointF(0.0, 0.0)

        def _emit_changed(self) -> None:
            self._points = _safe_normalize(self._points)
            try:
                self.pointsChanged.emit(self.points())
            except Exception:
                pass
            self.update()

        def _move_point(self, index: int, x: float, y: float) -> None:
            """Mutate a single point. Caller must call ``_emit_changed()`` after."""
            pts = list(self._points)
            if not pts or index < 0 or index >= len(pts):
                return
            y = _safe_clamp(y, 0.0, 2.0)
            if index in (0, len(pts) - 1):
                y_wrap = y
                pts[0] = (0.0, y_wrap)
                pts[-1] = (1.0, y_wrap)
                self._points = pts
                return

            left_x = pts[index - 1][0] + 1e-4
            right_x = pts[index + 1][0] - 1e-4
            x = _safe_clamp(x, left_x, right_x)
            pts[index] = (x, y)
            self._points = pts

        # ---- Paint (wrapped so a bad draw never crashes Nuke) ----

        def paintEvent(self, _event) -> None:  # pragma: no cover - GUI behavior
            try:
                self._paint_impl()
            except Exception:
                # If painting fails, draw a minimal placeholder so the panel
                # stays functional rather than crashing.
                try:
                    p = QPainter(self)
                    p.fillRect(self.rect(), QColor("#202326"))
                    p.end()
                except Exception:
                    pass

        def _paint_impl(self) -> None:
            painter = QPainter(self)
            try:
                if _Antialiasing is not None:
                    painter.setRenderHint(_Antialiasing, True)

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

                _EPSILON = 1e-6
                y_labels = ((0.0, "-180"), (0.5, "-90"), (1.0, "0"), (1.5, "+90"), (2.0, "+180"))
                for value, label in y_labels:
                    y = self._to_canvas(0.0, value).y()
                    pen = QPen(QColor(255, 255, 255, 60), 1.0)
                    if abs(value - 1.0) < _EPSILON:
                        if _DashLine is not None:
                            pen = QPen(QColor(255, 255, 255, 120), 1.2, _DashLine)
                        else:
                            pen = QPen(QColor(255, 255, 255, 120), 1.2)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                    painter.setPen(QPen(QColor("#d9d9d9"), 1.0))
                    painter.drawText(QPointF(8.0, y + 4.0), label)

                spline = QPainterPath()
                samples = max(int(plot.width()), 180)
                for idx in range(samples + 1):
                    x = idx / float(samples)
                    y = _safe_clamp(_safe_catmull_rom_y(self._points, x), 0.0, 2.0)
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
                painter.drawText(QPointF(plot.left(), float(self.height()) - 6.0), "0\u00b0")
                painter.drawText(QPointF(plot.right() - 30.0, float(self.height()) - 6.0), "360\u00b0")
            finally:
                painter.end()

        # ---- Mouse events (wrapped) ----

        def mousePressEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            try:
                self._mouse_press_impl(event)
            except Exception:
                pass

        def _mouse_press_impl(self, event) -> None:
            btn = event.button()
            if btn not in (_LeftButton, _RightButton):
                return

            pos = self._event_pos(event)
            idx = self._hit_test(pos)
            if btn == _RightButton:
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
                self._points = _safe_normalize(pts)
                self._drag_index = self._hit_test(pos)
                self._emit_changed()
                return

            self._drag_index = idx

        def mouseMoveEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            try:
                if self._drag_index is None:
                    return
                x, y = self._from_canvas(self._event_pos(event))
                self._move_point(self._drag_index, x, y)
                self._emit_changed()
            except Exception:
                self._drag_index = None

        def mouseReleaseEvent(self, _event) -> None:  # pragma: no cover - GUI behavior
            self._drag_index = None

        def mouseDoubleClickEvent(self, event) -> None:  # pragma: no cover - GUI behavior
            try:
                if event.button() != _LeftButton:
                    return
                idx = self._hit_test(self._event_pos(event))
                if idx is None:
                    return
                x = self._points[idx][0]
                self._move_point(idx, x, 1.0)
                self._emit_changed()
            except Exception:
                pass

    class HueCurveWidget:
        """PyCustom wrapper object that builds/returns a QWidget in makeUI()."""

        def __init__(self, node) -> None:
            self._node = node
            self._points: list[tuple[float, float]] = _default_points()
            self._container: Optional[QWidget] = None
            self._canvas: Optional[_HueCurveCanvas] = None
            self._reset: Optional[QPushButton] = None
            self._is_updating = False

        def makeUI(self):  # pragma: no cover - host integration only
            try:
                return self._make_ui_impl()
            except Exception:
                # If widget construction fails, return a minimal placeholder
                # so Nuke's panel system has a valid QWidget.
                try:
                    w = QWidget()
                    w.setMinimumHeight(2)
                    return w
                except Exception:
                    return None

        def _make_ui_impl(self):
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
                self._points = self._load_points_from_knob()
                self._canvas.set_points(self._points)
            except Exception:
                pass
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
                    return _safe_normalize(data)
                except Exception:
                    pass

            # Legacy fallback: read existing HueCorrect sat curve.
            try:
                hc = self._node.node("HueCorrect_HueCurves") if self._node is not None else None
                hue_knob = hc.knob("hue") if hc is not None else None
                if hue_knob is not None and _hcd is not None:
                    legacy = _hcd.parse_hue_script_points(hue_knob.toScript())
                    if legacy is not None and len(legacy) >= 2:
                        return legacy
            except Exception:
                pass
            return _default_points()

        def _save_points_to_knob(self) -> None:
            if _hcd is None:
                return
            knob = self._curve_data_knob()
            if knob is None:
                return
            try:
                knob.setValue(_hcd.points_to_json(self._points))
            except Exception:
                pass

        def _push_curve_to_huecorrect(self) -> None:
            if self._node is None or _hcd is None:
                return
            try:
                hc = self._node.node("HueCorrect_HueCurves")
                hue_knob = hc.knob("hue") if hc is not None else None
                if hue_knob is None:
                    return
                hue_knob.fromScript(_hcd.points_to_hue_script(self._points))
            except Exception as exc:
                try:
                    status = self._node.knob("status_text")
                    if status is not None:
                        msg = str(exc).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        status.setValue(
                            "<font color='#cc6666'><small><b>Status:</b> "
                            "HueCorrect curve update failed: {}</small></font>".format(msg)
                        )
                except Exception:
                    pass

        def _on_curve_changed(self, points: Iterable[Iterable[float]]) -> None:
            if self._is_updating:
                return
            try:
                self._points = _safe_normalize(points)
                self._save_points_to_knob()
                self._push_curve_to_huecorrect()
            except Exception:
                pass

        def _reset_curve(self) -> None:
            try:
                self._points = _default_points()
                if self._canvas is not None:
                    self._canvas.set_points(self._points)
                self._save_points_to_knob()
                self._push_curve_to_huecorrect()
            except Exception:
                pass


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
