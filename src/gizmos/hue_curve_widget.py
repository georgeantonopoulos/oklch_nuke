"""Custom Qt hue-curve widget for OKLCH_Grade gizmo.

Supports both PySide6 (Nuke 16+) and PySide2 (Nuke 14-15).

IMPORTANT — Nuke's PyCustom_Knob lifecycle:
  Nuke evaluates the knob's command string, which must return an object with
  makeUI() and updateValue() methods.  makeUI() must return a QWidget.
  The **canonical, crash-free** pattern is for the object itself to be a
  QWidget subclass and return ``self`` from makeUI().  The non-QWidget
  "wrapper" pattern causes garbage-collection segfaults in PySide6 because
  the wrapper can be collected while Nuke still references the child widget.
"""

from __future__ import annotations

import json
import os
from typing import Optional

try:
    import hue_curve_data as _hcd
except Exception:
    _hcd = None  # type: ignore[assignment]

try:
    import nuke
except Exception:
    nuke = None

# ---------------------------------------------------------------------------
# Qt import — PySide6 first, then PySide2
# ---------------------------------------------------------------------------
_HAS_QT = False

try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt  # type: ignore[import-untyped]
    from PySide6.QtGui import (  # type: ignore[import-untyped]
        QColor,
        QLinearGradient,
        QMouseEvent,
        QPainter,
        QPainterPath,
        QPen,
    )
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
        from PySide2.QtCore import QPointF, QRectF, QSize, Qt  # type: ignore[import-untyped,no-redef]
        from PySide2.QtGui import (  # type: ignore[import-untyped,no-redef]
            QColor,
            QLinearGradient,
            QMouseEvent,
            QPainter,
            QPainterPath,
            QPen,
        )
        from PySide2.QtWidgets import (  # type: ignore[import-untyped,no-redef]
            QHBoxLayout,
            QPushButton,
            QSizePolicy,
            QVBoxLayout,
            QWidget,
        )
        _HAS_QT = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PySide6 scoped-enum resolution (done once at import)
# ---------------------------------------------------------------------------
# PySide6 moved enums to scoped namespaces (Qt.MouseButton.LeftButton).
# Some Linux builds lack the compat shim, causing segfaults on the old form.

def _resolve(*candidates):
    """Try each dotted attribute path, return the first that resolves."""
    for obj, dotpath in candidates:
        try:
            for part in dotpath.split("."):
                obj = getattr(obj, part)
            return obj
        except (AttributeError, TypeError):
            continue
    return None


if _HAS_QT:
    _LeftButton = _resolve((Qt, "MouseButton.LeftButton"), (Qt, "LeftButton"))
    _RightButton = _resolve((Qt, "MouseButton.RightButton"), (Qt, "RightButton"))
    _DashLine = _resolve((Qt, "PenStyle.DashLine"), (Qt, "DashLine"))
    _Antialiasing = _resolve(
        (QPainter, "RenderHint.Antialiasing"), (QPainter, "Antialiasing")
    )
    _SizeExpanding = _resolve(
        (QSizePolicy, "Policy.Expanding"), (QSizePolicy, "Expanding")
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_POINT_RADIUS = 5.0
_HIT_RADIUS = 9.0
_EPSILON = 1e-6
_DEFAULT_POINTS = ((0.0, 1.0), (1.0, 1.0))

_RAINBOW_STOPS = (
    (0.00, "#ff4d4d"), (0.08, "#ff7f4d"), (0.17, "#ffbf4d"),
    (0.25, "#d4d84a"), (0.33, "#7ccf4a"), (0.42, "#4bcf86"),
    (0.50, "#47c8d8"), (0.58, "#4b9de6"), (0.67, "#5f79ef"),
    (0.75, "#8e67ef"), (0.83, "#bf62e8"), (0.92, "#e55eb8"),
    (1.00, "#ff4d4d"),
)


# ---------------------------------------------------------------------------
# Safe helpers that work even if hue_curve_data failed to import
# ---------------------------------------------------------------------------

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _normalize(points):
    if _hcd is not None:
        return _hcd.normalize_points(points)
    pts = []
    for pair in (points or []):
        try:
            x, y = pair
            pts.append((_clamp(float(x), 0.0, 1.0), _clamp(float(y), 0.0, 2.0)))
        except Exception:
            continue
    if len(pts) < 2:
        return list(_DEFAULT_POINTS)
    pts.sort(key=lambda p: p[0])
    pts[0] = (0.0, pts[0][1])
    pts[-1] = (1.0, pts[-1][1])
    return pts


def _catmull_y(points, x):
    if _hcd is not None:
        return _hcd.catmull_rom_y(points, x)
    if not points:
        return 1.0
    for i in range(len(points) - 1):
        if points[i][0] <= x <= points[i + 1][0]:
            dx = points[i + 1][0] - points[i][0]
            if dx < _EPSILON:
                return points[i][1]
            t = (x - points[i][0]) / dx
            return points[i][1] + t * (points[i + 1][1] - points[i][1])
    return points[-1][1]


def _defaults():
    if _hcd is not None:
        return list(_hcd._DEFAULT_POINTS)
    return list(_DEFAULT_POINTS)


# ---------------------------------------------------------------------------
# Fallback for headless / no-Qt sessions
# ---------------------------------------------------------------------------

class _FallbackWidget:
    def __init__(self, node):
        self._node = node

    def makeUI(self):
        if _HAS_QT:
            try:
                w = QWidget()
                w.setMinimumHeight(2)
                return w
            except Exception:
                return None
        return None

    def updateValue(self):
        return None


# ---------------------------------------------------------------------------
# The actual widget — a single QWidget subclass (canonical PyCustom pattern)
# ---------------------------------------------------------------------------

if _HAS_QT:

    class HueCurveWidget(QWidget):
        """PyCustom_Knob widget.  ``makeUI()`` returns ``self``.

        This follows the canonical Nuke pattern: the object *is* the QWidget,
        so Nuke's panel system holds a direct reference and PySide6's garbage
        collector cannot destroy it prematurely.
        """

        def __init__(self, node) -> None:
            super().__init__()
            self._node = node
            self._points = _defaults()
            self._drag_idx = None  # type: Optional[int]
            self._updating = False

            # --- Layout ------------------------------------------------
            self.setMinimumHeight(220)
            self.setToolTip(
                "Left-click: add/drag point | Right-click: remove "
                "| Double-click: reset to neutral (Y=1)"
            )
            try:
                if _SizeExpanding is not None:
                    self.setSizePolicy(_SizeExpanding, _SizeExpanding)
            except Exception:
                pass
            self.setMouseTracking(True)

            # Reset button lives in a layout over the paint area
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addStretch(1)
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            self._reset_btn = QPushButton("Reset")
            self._reset_btn.clicked.connect(self._reset_curve)
            btn_row.addWidget(self._reset_btn)
            layout.addLayout(btn_row)

        # ---- PyCustom_Knob protocol ----

        def makeUI(self):
            """Return self — the canonical pattern Nuke expects."""
            self.updateValue()
            return self

        def updateValue(self):
            """Called by Nuke when the panel opens or knob values change."""
            self._updating = True
            try:
                self._points = self._load_points()
                self.update()
            except Exception:
                pass
            finally:
                self._updating = False

        # ---- Geometry helpers ----

        def sizeHint(self):
            return QSize(420, 220)

        def _plot_rect(self):
            m_l, m_r, m_t, m_b = 48.0, 14.0, 14.0, 24.0
            w = max(10.0, float(self.width()) - m_l - m_r)
            h = max(10.0, float(self.height()) - m_t - m_b)
            return QRectF(m_l, m_t, w, h)

        def _to_canvas(self, x, y):
            r = self._plot_rect()
            return QPointF(
                r.left() + _clamp(x, 0.0, 1.0) * r.width(),
                r.top() + ((2.0 - _clamp(y, 0.0, 2.0)) / 2.0) * r.height(),
            )

        def _from_canvas(self, pt):
            r = self._plot_rect()
            x = (pt.x() - r.left()) / max(r.width(), 1.0)
            y = 2.0 - 2.0 * ((pt.y() - r.top()) / max(r.height(), 1.0))
            return (_clamp(x, 0.0, 1.0), _clamp(y, 0.0, 2.0))

        def _hit(self, pt):
            for i, (x, y) in enumerate(self._points):
                c = self._to_canvas(x, y)
                dx, dy = c.x() - pt.x(), c.y() - pt.y()
                if dx * dx + dy * dy <= _HIT_RADIUS * _HIT_RADIUS:
                    return i
            return None

        @staticmethod
        def _event_pos(event):
            """Get local pos, Qt6 and Qt5 safe."""
            for method in ("position", "localPos", "posF"):
                try:
                    pos = getattr(event, method)()
                    return pos if isinstance(pos, QPointF) else QPointF(pos)
                except (AttributeError, TypeError):
                    continue
            try:
                return QPointF(event.pos())
            except Exception:
                return QPointF(0.0, 0.0)

        # ---- Point manipulation ----

        def _move_point(self, idx, x, y):
            pts = list(self._points)
            if idx < 0 or idx >= len(pts):
                return
            y = _clamp(y, 0.0, 2.0)
            if idx in (0, len(pts) - 1):
                pts[0] = (0.0, y)
                pts[-1] = (1.0, y)
                self._points = pts
                return
            left = pts[idx - 1][0] + 1e-4
            right = pts[idx + 1][0] - 1e-4
            pts[idx] = (_clamp(x, left, right), y)
            self._points = pts

        def _commit(self):
            """Normalize, save, push to HueCorrect, repaint."""
            self._points = _normalize(self._points)
            self._save_points()
            self._push_huecorrect()
            self.update()

        # ---- Paint ----

        def paintEvent(self, _ev):
            try:
                self._paint()
            except Exception:
                try:
                    p = QPainter(self)
                    p.fillRect(self.rect(), QColor("#202326"))
                    p.end()
                except Exception:
                    pass

        def _paint(self):
            p = QPainter(self)
            try:
                if _Antialiasing is not None:
                    p.setRenderHint(_Antialiasing, True)

                plot = self._plot_rect()

                # Background
                p.fillRect(self.rect(), QColor("#202326"))
                grad = QLinearGradient(plot.left(), plot.top(), plot.right(), plot.top())
                for pos, col in _RAINBOW_STOPS:
                    grad.setColorAt(pos, QColor(col))
                p.fillRect(plot, grad)

                # Vertical grid
                p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
                for deg in (0, 60, 120, 180, 240, 300, 360):
                    x = plot.left() + (deg / 360.0) * plot.width()
                    p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

                # Horizontal grid + Y labels
                for val, label in ((0.0, "-180"), (0.5, "-90"), (1.0, "0"),
                                   (1.5, "+90"), (2.0, "+180")):
                    cy = self._to_canvas(0.0, val).y()
                    if abs(val - 1.0) < _EPSILON and _DashLine is not None:
                        p.setPen(QPen(QColor(255, 255, 255, 120), 1.2, _DashLine))
                    else:
                        alpha = 120 if abs(val - 1.0) < _EPSILON else 60
                        p.setPen(QPen(QColor(255, 255, 255, alpha), 1.0))
                    p.drawLine(QPointF(plot.left(), cy), QPointF(plot.right(), cy))
                    p.setPen(QPen(QColor("#d9d9d9"), 1.0))
                    p.drawText(QPointF(8.0, cy + 4.0), label)

                # Spline
                path = QPainterPath()
                samples = max(int(plot.width()), 180)
                for i in range(samples + 1):
                    sx = i / float(samples)
                    sy = _clamp(_catmull_y(self._points, sx), 0.0, 2.0)
                    pt = self._to_canvas(sx, sy)
                    if i == 0:
                        path.moveTo(pt)
                    else:
                        path.lineTo(pt)
                p.setPen(QPen(QColor("#121416"), 4.0))
                p.drawPath(path)
                p.setPen(QPen(QColor("#f5f7ff"), 2.0))
                p.drawPath(path)

                # Control points
                for cx, cy in self._points:
                    cp = self._to_canvas(cx, cy)
                    p.setBrush(QColor("#121416"))
                    p.setPen(QPen(QColor("#f5f7ff"), 2.0))
                    p.drawEllipse(cp, _POINT_RADIUS + 1, _POINT_RADIUS + 1)
                    p.setBrush(QColor("#75c7ff"))
                    p.drawEllipse(cp, _POINT_RADIUS - 1.5, _POINT_RADIUS - 1.5)

                # X axis labels
                p.setPen(QPen(QColor("#d9d9d9"), 1.0))
                p.drawText(QPointF(plot.left(), float(self.height()) - 6), "0\u00b0")
                p.drawText(QPointF(plot.right() - 30, float(self.height()) - 6), "360\u00b0")
            finally:
                p.end()

        # ---- Mouse events ----

        def mousePressEvent(self, ev):
            try:
                self._on_press(ev)
            except Exception:
                pass

        def _on_press(self, ev):
            btn = ev.button()
            if btn not in (_LeftButton, _RightButton):
                return
            pos = self._event_pos(ev)
            idx = self._hit(pos)

            if btn == _RightButton:
                if idx is not None and idx not in (0, len(self._points) - 1):
                    pts = list(self._points)
                    pts.pop(idx)
                    self._points = pts
                    self._commit()
                return

            if idx is None:
                x, y = self._from_canvas(pos)
                pts = list(self._points)
                ins = 1
                while ins < len(pts) and pts[ins][0] < x:
                    ins += 1
                pts.insert(ins, (x, y))
                self._points = _normalize(pts)
                self._drag_idx = self._hit(pos)
                self._commit()
                return

            self._drag_idx = idx

        def mouseMoveEvent(self, ev):
            try:
                if self._drag_idx is None:
                    return
                x, y = self._from_canvas(self._event_pos(ev))
                self._move_point(self._drag_idx, x, y)
                self._commit()
            except Exception:
                self._drag_idx = None

        def mouseReleaseEvent(self, _ev):
            self._drag_idx = None

        def mouseDoubleClickEvent(self, ev):
            try:
                if ev.button() != _LeftButton:
                    return
                idx = self._hit(self._event_pos(ev))
                if idx is None:
                    return
                self._move_point(idx, self._points[idx][0], 1.0)
                self._commit()
            except Exception:
                pass

        # ---- Knob I/O ----

        def _knob(self, name):
            if self._node is None:
                return None
            try:
                return self._node.knob(name)
            except Exception:
                return None

        def _load_points(self):
            knob = self._knob("hue_curve_data")
            if knob is not None:
                try:
                    raw = str(knob.value() or "")
                    if raw.strip():
                        return _normalize(json.loads(raw))
                except Exception:
                    pass
            # Legacy: migrate from HueCorrect sat curve
            if _hcd is not None and self._node is not None:
                try:
                    hc = self._node.node("HueCorrect_HueCurves")
                    hk = hc.knob("hue") if hc else None
                    if hk is not None:
                        legacy = _hcd.parse_hue_script_points(hk.toScript())
                        if legacy and len(legacy) >= 2:
                            return legacy
                except Exception:
                    pass
            return _defaults()

        def _save_points(self):
            if _hcd is None:
                return
            knob = self._knob("hue_curve_data")
            if knob is None:
                return
            try:
                knob.setValue(_hcd.points_to_json(self._points))
            except Exception:
                pass

        def _push_huecorrect(self):
            if self._node is None or _hcd is None:
                return
            try:
                hc = self._node.node("HueCorrect_HueCurves")
                hk = hc.knob("hue") if hc else None
                if hk is None:
                    return
                hk.fromScript(_hcd.points_to_hue_script(self._points))
            except Exception:
                pass

        def _reset_curve(self):
            try:
                self._points = _defaults()
                self._commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Factory — the string evaluated by the PyCustom_Knob
# ---------------------------------------------------------------------------

def create_widget(node):
    """Entrypoint called by PyCustom_Knob command string."""
    if os.environ.get("OKLCH_DISABLE_HUE_CURVE_WIDGET", "").strip().lower() in (
        "1", "true", "yes",
    ):
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
