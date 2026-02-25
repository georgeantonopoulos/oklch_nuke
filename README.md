# OKLCH Grade for Nuke (BlinkScript)

A Nuke gizmo + Blink kernel that performs grading in OKLCH while converting from/to user-selected OCIO colorspaces.

## What this repository contains

- `src/blink/oklch_grade_kernel.cpp`
  - Blink kernel implementing linear-sRGB <-> OKLab/OKLCH conversion and grade controls.
- `src/gizmos/OKLCH_Grade.gizmo`
  - Group/gizmo wrapper with input/output colorspace dropdowns and user controls.
- `tools/oklch_grade_init.py`
  - Archived initialization helper kept for rebuilding/regenerating the gizmo authoring workflow.
  - Not used by runtime startup/menu loading.
- `research/`
  - Source-backed notes for Blink syntax, OCIO wiring, and OKLCH math constants.
- `tests/oklch_reference_test_vectors.md`
  - Manual validation vectors and acceptance checks.

## Node architecture

`Input` -> `OCIOColorSpace_IN` (to detected linear-sRGB working space) -> `BlinkScript_OKLCHGrade` -> `OCIOColorSpace_OUT` (back to output space) -> `Output`

## Controls

Public controls on the gizmo:

- `input_colorspace`
- `output_colorspace`
- `l_gain`
- `l_offset`
- `l_contrast`
- `l_pivot`
- `c_gain`
- `c_offset`
- `hue_shift_deg`
- `hue_chroma_threshold`
- `hue_shift_red`
- `hue_shift_yellow`
- `hue_shift_green`
- `hue_shift_cyan`
- `hue_shift_blue`
- `hue_shift_magenta`
- `hue_target_deg`
- `hue_target_shift`
- `hue_target_falloff_deg`
- `mix`
- `clamp_output`
- `bypass`

## Internal working-space behavior

The gizmo compiles the BlinkScript kernel from inline `kernelSource` at instantiation time (`isBaked false`) and exposes pre-linked controls.
Menu scripts only register plugin paths and add the gizmo creation command.

## Installation

1. Add either of these to `NUKE_PATH`:
   - `/Users/georgeantonopoulos/Dev/oklch_nuke` (recommended), or
   - `/Users/georgeantonopoulos/Dev/oklch_nuke/src`
2. Restart Nuke.
3. Nuke startup hooks used by this repo:
   - `init.py` for non-UI bootstrap (plugin paths)
   - `menu.py` for UI registration (single gizmo menu command)
4. The UI hook adds:
   - `Nodes > Color > OKLCH > OKLCH Grade`
   - icon: `oklch_grade.png`
5. Create `OKLCH_Grade` from that menu or tab search.

Example `NUKE_PATH` setup (repo-root form):

- macOS/Linux: `export NUKE_PATH=\"/Users/georgeantonopoulos/Dev/oklch_nuke:$NUKE_PATH\"`
- Windows: `set NUKE_PATH=C:\\path\\to\\oklch_nuke;%NUKE_PATH%`

## Quick diagnostics in Nuke Script Editor

```python
import nuke
print("plugin paths:", nuke.pluginPath())
try:
    node = nuke.createNode("OKLCH_Grade", inpanel=False)
    print("OKLCH_Grade creation: OK")
    nuke.delete(node)
except Exception as exc:
    print("OKLCH_Grade creation failed:", exc)
```

If node creation fails, your `NUKE_PATH` is not pointing at the expected location or startup scripts are not being executed.

## Verification checklist

Use `tests/oklch_reference_test_vectors.md` to validate:

- identity round-trip epsilon (`<= 1e-5`)
- achromatic hue stability
- hue wrap
- unclamped vs clamped range policy
- alpha passthrough
- fail-safe behavior when no linear-sRGB alias exists

## References

See `research/README.md` for all source links.
