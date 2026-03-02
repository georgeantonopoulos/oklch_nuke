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

from datetime import datetime
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
_QT_API = "none"

_WIDGET_MODE_ENV = "OKLCH_HUE_WIDGET_MODE"
_WIDGET_DEBUG_ENV = "OKLCH_HUE_WIDGET_DEBUG"
_WIDGET_DEBUG_LOG_ENV = "OKLCH_HUE_WIDGET_LOG"

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
    _QT_API = "PySide6"
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
        _QT_API = "PySide2"
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
# Diagnostics
# ---------------------------------------------------------------------------

def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _node_name(node) -> str:
    if node is None:
        return "<none>"
    try:
        return str(node.fullName())
    except Exception:
        try:
            return str(node.name())
        except Exception:
            return "<unknown>"


def _widget_mode() -> str:
    raw = os.environ.get(_WIDGET_MODE_ENV, "full").strip().lower()
    aliases = {"interactive": "full", "disabled": "off"}
    mode = aliases.get(raw, raw)
    if mode not in ("off", "readonly", "full"):
        return "full"
    return mode


def _debug_enabled() -> bool:
    return _is_truthy(os.environ.get(_WIDGET_DEBUG_ENV, ""))


def _debug(message: str, *, node=None, error: Optional[Exception] = None) -> None:
    if not _debug_enabled():
        return
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = (
        f"[{ts}] pid={os.getpid()} mode={_widget_mode()} node={_node_name(node)} "
        f"{message}"
    )
    if error is not None:
        line += f" error={error!r}"

    try:
        if nuke is not None and hasattr(nuke, "tprint"):
            nuke.tprint(f"[OKLCH HueWidget] {line}")
        else:
            print(f"[OKLCH HueWidget] {line}")
    except Exception:
        pass

    log_path = os.environ.get(_WIDGET_DEBUG_LOG_ENV, "").strip()
    if not log_path:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


_debug(f"module_loaded has_qt={_HAS_QT} qt_api={_QT_API}", node=None)
if _HAS_QT:
    _debug(
        "enum_resolution "
        f"left={_LeftButton is not None} right={_RightButton is not None} "
        f"dash={_DashLine is not None} aa={_Antialiasing is not None}",
        node=None,
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
        return _hcd._catmull_rom_y_normalized(points, x)
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
    def __init__(self, node, reason: str = ""):
        self._node = node
        self._reason = reason

    def makeUI(self):
        _debug(f"fallback.makeUI reason={self._reason or '<none>'}", node=self._node)
        if _HAS_QT:
            try:
                w = QWidget()
                w.setMinimumHeight(2)
                return w
            except Exception as exc:
                _debug("fallback.makeUI failed", node=self._node, error=exc)
                return None
        return None

    def updateValue(self):
        _debug(f"fallback.updateValue reason={self._reason or '<none>'}", node=self._node)
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

        def __init__(
            self,
            node,
            *,
            allow_edit: bool = True,
            push_runtime_lut: bool = True,
            show_reset_button: bool = True,
        ) -> None:
            super().__init__()
            self._node = node
            self._points = _defaults()
            self._drag_idx = None  # type: Optional[int]
            self._updating = False
            self._allow_edit = allow_edit
            self._push_runtime_lut = push_runtime_lut
            self._show_reset_button = show_reset_button
            _debug(
                "widget.init "
                f"allow_edit={self._allow_edit} "
                f"push_runtime_lut={self._push_runtime_lut} "
                f"reset_btn={self._show_reset_button}",
                node=self._node,
            )

            # --- Layout ------------------------------------------------
            self.setMinimumHeight(220)
            if self._allow_edit:
                self.setToolTip(
                    "Left-click: add/drag point | Right-click: remove "
                    "| Double-click: reset to neutral (Y=1)"
                )
            else:
                self.setToolTip("Read-only diagnostic mode (editing disabled).")
            try:
                if _SizeExpanding is not None:
                    self.setSizePolicy(_SizeExpanding, _SizeExpanding)
            except Exception as exc:
                _debug("widget.setSizePolicy failed", node=self._node, error=exc)
                pass
            self.setMouseTracking(True)

            if self._show_reset_button:
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
            _debug("widget.makeUI", node=self._node)
            self.updateValue()
            return self

        def updateValue(self):
            """Called by Nuke when the panel opens or knob values change."""
            _debug("widget.updateValue.start", node=self._node)
            self._updating = True
            try:
                self._points = self._load_points()
                self.update()
            except Exception as exc:
                _debug("widget.updateValue failed", node=self._node, error=exc)
            finally:
                self._updating = False
                _debug("widget.updateValue.end", node=self._node)

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

        def _commit_drag(self):
            """Normalize, push LUT expression, repaint — skip save and wiring checks."""
            self._points = _normalize(self._points)
            if self._allow_edit and self._push_runtime_lut:
                self._push_direct_lut_expression()
            self.update()

        def _commit(self):
            """Normalize, save, push direct LUT expression, repaint."""
            self._points = _normalize(self._points)
            if self._allow_edit:
                self._save_points()
            if self._allow_edit and self._push_runtime_lut:
                self._sync_lut_runtime_state()
                self._push_direct_lut_expression()
            self.update()

        # ---- Paint ----

        def paintEvent(self, _ev):
            try:
                self._paint()
            except Exception as exc:
                _debug("widget.paintEvent failed", node=self._node, error=exc)
                try:
                    p = QPainter(self)
                    p.fillRect(self.rect(), QColor("#202326"))
                    p.end()
                except Exception as fallback_exc:
                    _debug("widget.paintEvent fallback failed", node=self._node, error=fallback_exc)
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
                if not self._allow_edit:
                    return
                self._on_press(ev)
            except Exception as exc:
                _debug("widget.mousePressEvent failed", node=self._node, error=exc)

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
                if not self._allow_edit:
                    return
                if self._drag_idx is None:
                    return
                x, y = self._from_canvas(self._event_pos(ev))
                self._move_point(self._drag_idx, x, y)
                self._commit_drag()
            except Exception as exc:
                _debug("widget.mouseMoveEvent failed", node=self._node, error=exc)
                self._drag_idx = None

        def mouseReleaseEvent(self, _ev):
            if self._drag_idx is not None:
                self._commit()
            self._drag_idx = None

        def mouseDoubleClickEvent(self, ev):
            try:
                if not self._allow_edit:
                    return
                if ev.button() != _LeftButton:
                    return
                idx = self._hit(self._event_pos(ev))
                if idx is None:
                    return
                self._move_point(idx, self._points[idx][0], 1.0)
                self._commit()
            except Exception as exc:
                _debug("widget.mouseDoubleClickEvent failed", node=self._node, error=exc)

        # ---- Knob I/O ----

        @staticmethod
        def _node_knob(node, name):
            if node is None:
                return None
            try:
                return node.knob(name)
            except Exception:
                return None

        def _knob(self, name):
            if self._node is None:
                return None
            try:
                return self._node.knob(name)
            except Exception:
                return None

        def _set_status(self, html: str) -> None:
            knob = self._knob("status_text")
            if knob is None:
                return
            try:
                knob.setValue(html)
            except Exception:
                pass

        def _set_blink_param_if_exists(self, blink, internal_name: str, label: str, value) -> bool:
            if blink is None:
                return False
            candidates = (
                internal_name,
                f"OKLCHGrade_{label}",
                f"OKLCHGrade_{label.replace(' ', '_')}",
            )
            for name in candidates:
                knob = self._node_knob(blink, name)
                if knob is None:
                    continue
                try:
                    knob.setValue(value)
                    return True
                except Exception:
                    continue
            return False

        def _sync_lut_runtime_state(self) -> None:
            """Ensure Blink input wiring + LUT params are valid during floating edits."""
            if self._node is None:
                return

            blink = self._node.node("BlinkScript_OKLCHGrade")
            expr = self._node.node("Expression_HueRamp")
            ocio_in = self._node.node("OCIOColorSpace_IN")
            if blink is None:
                return

            try:
                if ocio_in is not None and blink.input(0) is not ocio_in:
                    blink.setInput(0, ocio_in)
            except Exception as exc:
                _debug("widget._sync_lut_runtime_state input0 wiring failed", node=self._node, error=exc)

            try:
                if expr is not None and blink.input(1) is not expr:
                    blink.setInput(1, expr)
            except Exception as exc:
                _debug("widget._sync_lut_runtime_state input1 wiring failed", node=self._node, error=exc)

            connected = False
            try:
                connected = expr is not None and blink.input(1) is expr
            except Exception:
                connected = False

            width = 360
            try:
                if expr is not None:
                    width = max(int(expr.format().width()), 2)
            except Exception:
                width = 360

            self._set_blink_param_if_exists(blink, "hue_lut_width", "Hue LUT Width", width)
            self._set_blink_param_if_exists(blink, "hue_lut_connected", "Hue LUT Connected", connected)
            self._set_blink_param_if_exists(blink, "hue_curves_enable", "Hue Curves Enable", True)

            enable_knob = self._knob("hue_curves_enable")
            if enable_knob is not None:
                try:
                    if not bool(enable_knob.value()):
                        enable_knob.setValue(True)
                except Exception:
                    try:
                        enable_knob.setValue(True)
                    except Exception:
                        pass

        def _load_points(self):
            knob = self._knob("hue_curve_data")
            if knob is not None:
                try:
                    raw = str(knob.value() or "")
                    if raw.strip():
                        return _normalize(json.loads(raw))
                except Exception as exc:
                    _debug("widget._load_points json parse failed", node=self._node, error=exc)
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
                except Exception as exc:
                    _debug("widget._load_points legacy migration failed", node=self._node, error=exc)
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
            except Exception as exc:
                _debug("widget._save_points failed", node=self._node, error=exc)

        def _push_direct_lut_expression(self):
            if self._node is None or _hcd is None:
                return
            try:
                expr = self._node.node("Expression_HueRamp")
                if expr is None:
                    self._set_status(
                        "<font color='#cc6666'><small><b>Status:</b> Floating editor: Expression_HueRamp node missing.</small></font>"
                    )
                    return
                expr_lut = _hcd.points_to_lut_expression(self._points, x_var="lutx")
                temp_name0 = self._node_knob(expr, "temp_name0")
                temp_expr0 = self._node_knob(expr, "temp_expr0")
                expr0 = self._node_knob(expr, "expr0")
                expr1 = self._node_knob(expr, "expr1")
                expr2 = self._node_knob(expr, "expr2")
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
                self._set_status(
                    "<font color='#66AA66'><small><b>Status:</b> Floating editor updated direct hue LUT.</small></font>"
                )
            except Exception as exc:
                _debug("widget._push_direct_lut_expression failed", node=self._node, error=exc)
                try:
                    self._set_status(
                        "<font color='#cc6666'><small><b>Status:</b> Floating editor failed to apply direct LUT. Check Script Editor.</small></font>"
                    )
                    if nuke is not None and hasattr(nuke, "tprint"):
                        nuke.tprint(f"[OKLCH HueWidget] direct LUT update failure: {exc!r}")
                except Exception:
                    pass

        def _reset_curve(self):
            try:
                if not self._allow_edit:
                    return
                self._points = _defaults()
                self._commit()
            except Exception as exc:
                _debug("widget._reset_curve failed", node=self._node, error=exc)


# ---------------------------------------------------------------------------
# Factory — the string evaluated by the PyCustom_Knob
# ---------------------------------------------------------------------------

def create_widget(node):
    """Entrypoint called by PyCustom_Knob command string."""
    if _is_truthy(os.environ.get("OKLCH_DISABLE_HUE_CURVE_WIDGET", "")):
        return _FallbackWidget(node, reason="OKLCH_DISABLE_HUE_CURVE_WIDGET")

    if not _HAS_QT:
        return _FallbackWidget(node, reason="qt_unavailable")

    if nuke is not None:
        try:
            if not nuke.GUI():
                return _FallbackWidget(node, reason="non_gui_session")
        except Exception as exc:
            _debug("create_widget nuke.GUI check failed", node=node, error=exc)
            pass

    mode = _widget_mode()
    _debug(f"create_widget mode={mode}", node=node)
    if mode == "off":
        return _FallbackWidget(node, reason=f"{_WIDGET_MODE_ENV}=off")

    try:
        if mode == "readonly":
            return HueCurveWidget(
                node,
                allow_edit=False,
                push_runtime_lut=False,
                show_reset_button=False,
            )
        return HueCurveWidget(node)
    except Exception as exc:
        _debug("create_widget failed, falling back", node=node, error=exc)
        return _FallbackWidget(node, reason="widget_construction_failed")
