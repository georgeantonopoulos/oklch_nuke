"""
Nuke startup bootstrap (non-UI).

Purpose:
- ensure the bundled python helpers in `src/nuke` are importable in all
  sessions (GUI and headless) so gizmo callbacks can import `oklch_grade_init`.

UI concerns such as menu/toolbar registration are handled in `menu.py`.
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
    nuke_dir = os.path.join(root, "nuke")

    # Keep plugin-path wiring in menu.py; here we only ensure Python imports.
    if os.path.isdir(nuke_dir) and nuke_dir not in sys.path:
        sys.path.insert(0, nuke_dir)


_bootstrap_python_imports()
