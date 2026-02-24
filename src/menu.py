"""
Nuke UI bootstrap.

Nuke executes `menu.py` for each directory in NUKE_PATH when running with UI.
This file registers the gizmo directory and adds a Nodes menu command.
"""

import os
import importlib

import nuke

_this_dir = os.path.dirname(os.path.abspath(__file__))
_gizmos_dir = os.path.join(_this_dir, "gizmos")
_icons_dir = os.path.join(_gizmos_dir, "icons")
_CALLBACK_GUARD_ATTR = "_oklch_grade_init_callbacks_registered"

nuke.pluginAddPath(_gizmos_dir)
nuke.pluginAddPath(_icons_dir)

t = nuke.menu("Nodes")
u = t.addMenu("OKLCH", icon="oklch_grade.png")
u.addCommand("OKLCH Grade", "nuke.createNode('OKLCH_Grade')", icon="oklch_grade.png")


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
    if getattr(nuke, _CALLBACK_GUARD_ATTR, False):
        return
    nuke.addOnUserCreate(_init_from_this_node)
    nuke.addOnCreate(_init_from_this_node)
    setattr(nuke, _CALLBACK_GUARD_ATTR, True)


def _init_existing_nodes() -> None:
    for node in nuke.allNodes("Group", recurseGroups=True):
        _run_oklch_init_for_node(node)


_register_init_callbacks()
_init_existing_nodes()
