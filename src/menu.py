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

if not getattr(nuke, _MENU_GUARD_ATTR, False):
    t = nuke.menu("Nodes")
    t.addCommand("Color/OKLCH/OKLCH Grade", "nuke.createNode('OKLCH_Grade')", icon="oklch_grade.png")
    setattr(nuke, _MENU_GUARD_ATTR, True)
