"""
Repository-root Nuke UI bootstrap.

This supports installs where NUKE_PATH points to the repository root.
It mirrors `src/menu.py` behavior and keeps registration duplicate-safe.
"""

from __future__ import annotations

import os
import importlib

import nuke

MENU_GUARD_ATTR = "_oklch_grade_menu_registered"
CALLBACK_GUARD_ATTR = "_oklch_grade_init_callbacks_registered"


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


def _is_oklch_grade_group(node) -> bool:
    try:
        if node is None or node.Class() != "Group":
            return False
        return node.node("BlinkScript_OKLCHGrade") is not None
    except Exception:
        return False


def _run_oklch_init_for_node(node) -> None:
    if not _is_oklch_grade_group(node):
        return
    try:
        import oklch_grade_init
        importlib.reload(oklch_grade_init)
        oklch_grade_init.initialize_node(node)
    except Exception as exc:
        try:
            k = node.knob("status_text")
            if k is not None:
                k.setValue(f"Init error: {exc}")
        except Exception:
            pass


def _init_from_this_node() -> None:
    _run_oklch_init_for_node(nuke.thisNode())


def _register_init_callbacks() -> None:
    if getattr(nuke, CALLBACK_GUARD_ATTR, False):
        return
    nuke.addOnUserCreate(_init_from_this_node)
    nuke.addOnCreate(_init_from_this_node)
    setattr(nuke, CALLBACK_GUARD_ATTR, True)


def _init_existing_nodes() -> None:
    for node in nuke.allNodes("Group", recurseGroups=True):
        _run_oklch_init_for_node(node)


_register_plugin_paths()
_add_toolbar_entry()
_register_init_callbacks()
_init_existing_nodes()
