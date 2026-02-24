"""
Repository-root Nuke UI bootstrap.

This supports installs where NUKE_PATH points to the repository root.
It mirrors `src/menu.py` behavior and keeps registration duplicate-safe.
"""

from __future__ import annotations

import os

import nuke

MENU_GUARD_ATTR = "_oklch_grade_menu_registered"


def _register_plugin_paths() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    nuke_dir = os.path.join(root, "src", "gizmos")
    icons_dir = os.path.join(nuke_dir, "icons")

    if os.path.isdir(nuke_dir):
        nuke.pluginAddPath(nuke_dir)

    if os.path.isdir(icons_dir):
        nuke.pluginAddPath(icons_dir)


def _add_toolbar_entry() -> None:
    if getattr(nuke, MENU_GUARD_ATTR, False):
        return

    _this_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(_this_dir, "src", "gizmos", "icons", "oklch_grade.png")
    icon = icon_path if os.path.isfile(icon_path) else "oklch_grade.png"

    command = "nuke.createNode('OKLCH_Grade')"

    t = nuke.menu("Nodes")
    t.addCommand("Color/OKLCH/OKLCH Grade", command, icon=icon)


    setattr(nuke, MENU_GUARD_ATTR, True)


_register_plugin_paths()
_add_toolbar_entry()
