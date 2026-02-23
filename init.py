"""
Repository-root Nuke bootstrap.

This supports installs where NUKE_PATH points to the repository root.
It forwards loading to `src/` where the plugin implementation lives.
"""

from __future__ import annotations

import os

try:
    import nuke
except Exception:
    nuke = None


def _bootstrap_from_root() -> None:
    if nuke is None:
        return

    root = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(root, "src")

    if os.path.isdir(src_dir):
        # Triggers src/init.py so plugin resources are registered.
        nuke.pluginAddPath(src_dir)


_bootstrap_from_root()

