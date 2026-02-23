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

try:
    import nuke
except Exception:
    nuke = None


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


_bootstrap_python_imports()
