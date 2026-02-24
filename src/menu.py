"""
Nuke UI bootstrap.

Nuke executes `menu.py` for each directory in NUKE_PATH when running with UI.
This file registers the gizmo directory and adds a Nodes menu command.
"""

import os

import nuke

_this_dir = os.path.dirname(os.path.abspath(__file__))
_gizmos_dir = os.path.join(_this_dir, "gizmos")
_icons_dir = os.path.join(_gizmos_dir, "icons")
_MENU_GUARD_ATTR = "_oklch_grade_menu_registered"

nuke.pluginAddPath(_gizmos_dir)
nuke.pluginAddPath(_icons_dir)

def _add_menu_entries() -> None:
    if getattr(nuke, _MENU_GUARD_ATTR, False):
        return

    nodes_menu = nuke.menu("Nodes")
    if nodes_menu is None:
        return

    icon_path = os.path.join(_icons_dir, "oklch_grade.png")
    icon = icon_path if os.path.isfile(icon_path) else "oklch_grade.png"
    command = "nuke.createNode('OKLCH_Grade')"

    # Keep the canonical Color location.
    nodes_menu.addCommand("Color/OKLCH/OKLCH Grade", command, icon=icon)
    # Also expose top-level entry to avoid discoverability regressions.
    top = nodes_menu.addMenu("OKLCH", icon=icon)
    top.addCommand("OKLCH Grade", command, icon=icon)

    setattr(nuke, _MENU_GUARD_ATTR, True)


_add_menu_entries()
