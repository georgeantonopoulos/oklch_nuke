"""
Nuke UI bootstrap.

Nuke executes `menu.py` for each directory in NUKE_PATH when running with UI.
This file registers the gizmo directory and adds a toolbar/menu command.
"""

from __future__ import annotations

import os

import nuke


def _register_plugin_paths() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    nuke_dir = os.path.join(root, "nuke")
    icons_dir = os.path.join(nuke_dir, "icons")

    if os.path.isdir(nuke_dir):
        # Ensure gizmo + helper python module discovery from bundled folder.
        nuke.pluginAddPath(nuke_dir)

    if os.path.isdir(icons_dir):
        nuke.pluginAddPath(icons_dir)


def _add_toolbar_entry() -> None:
    nodes_menu = nuke.menu("Nodes")
    if nodes_menu is None:
        return

    color_menu = nodes_menu.addMenu("Color")
    oklch_menu = color_menu.addMenu("OKLCH")

    icon_name = "oklch_grade.png"
    command = "nuke.createNode('OKLCH_Grade')"
    oklch_menu.addCommand("OKLCH Grade", command, icon=icon_name)


_register_plugin_paths()
_add_toolbar_entry()

