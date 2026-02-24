"""
Nuke startup bootstrap (non-UI).

Purpose:
- register the bundled `nuke` plugin directory so gizmos/scripts are available
  in GUI and headless sessions.
- ensure `oklch_grade_init.py` is importable by gizmo callbacks.

UI concerns (toolbar/menu commands) are handled in `menu.py`.
"""

from __future__ import annotations

import os
import sys
import importlib

try:
    import nuke
except Exception:
    nuke = None

CALLBACK_GUARD_ATTR = "_oklch_grade_callbacks_registered"


def _bootstrap_python_imports() -> None:
    if nuke is None:
        return

    root = os.path.dirname(os.path.abspath(__file__))
    nuke_dir = os.path.join(root, "gizmos")

    if os.path.isdir(nuke_dir):
        # Register gizmos and helper scripts for all session types.
        nuke.pluginAddPath(nuke_dir)
        if nuke_dir not in sys.path:
            sys.path.insert(0, nuke_dir)


def _initialize_oklch_grade_node() -> None:
    """Initialize OKLCH_Grade node from a global onCreate callback."""
    if nuke is None:
        return
    node = None
    try:
        node = nuke.thisNode()
        import oklch_grade_init
        importlib.reload(oklch_grade_init)
        oklch_grade_init.initialize_node(node)
    except Exception as exc:
        try:
            if node is not None:
                k = node.knob("status_text")
                if k is not None:
                    k.setValue(f"Init error: {exc}")
        except Exception:
            pass


def _register_callbacks() -> None:
    if nuke is None:
        return
    if getattr(nuke, CALLBACK_GUARD_ATTR, False):
        return
    nuke.addOnCreate(_initialize_oklch_grade_node, nodeClass="OKLCH_Grade")
    setattr(nuke, CALLBACK_GUARD_ATTR, True)


_bootstrap_python_imports()
_register_callbacks()
