"""
Nuke UI bootstrap.

Nuke executes `menu.py` for each directory in NUKE_PATH when running with UI.
This file registers the gizmo directory and adds a toolbar/menu command.
"""

from __future__ import annotations

import os

import nuke

MENU_GUARD_ATTR = "_oklch_grade_menu_registered"


def _register_plugin_paths() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    nuke_dir = os.path.join(root, "gizmos")
    icons_dir = os.path.join(nuke_dir, "icons")

    if os.path.isdir(nuke_dir):
        # Ensure gizmo + helper python module discovery from bundled folder.
        nuke.pluginAddPath(nuke_dir)

    if os.path.isdir(icons_dir):
        nuke.pluginAddPath(icons_dir)


def _add_toolbar_entry() -> None:
    if getattr(nuke, MENU_GUARD_ATTR, False):
        return

    icon_name = "oklch_grade.png"
    command = "nuke.createNode('OKLCH_Grade')"
    menu_path = "Color/OKLCH/OKLCH Grade"

    # Add to Nodes toolbar (left-hand side)
    nodes_toolbar = nuke.toolbar("Nodes")
    if nodes_toolbar:
        nodes_toolbar.addCommand(menu_path, command, icon=icon_name)

    setattr(nuke, MENU_GUARD_ATTR, True)


_register_plugin_paths()
_add_toolbar_entry()
