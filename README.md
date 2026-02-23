# OKLCH Grade for Nuke (BlinkScript)

A Nuke gizmo + Blink kernel that performs grading in OKLCH while converting from/to user-selected OCIO colorspaces.

## What this repository contains

- `src/blink/oklch_grade_kernel.cpp`
  - Blink kernel implementing linear-sRGB <-> OKLab/OKLCH conversion and grade controls.
- `src/nuke/OKLCH_Grade.gizmo`
  - Group/gizmo wrapper with input/output colorspace dropdowns and user controls.
- `src/nuke/oklch_grade_init.py`
  - Python helpers for dynamic OCIO menu population, working-space detection, and internal node sync.
- `research/`
  - Source-backed notes for Blink syntax, OCIO wiring, and OKLCH math constants.
- `tests/oklch_reference_test_vectors.md`
  - Manual validation vectors and acceptance checks.

## Node architecture

`Input` -> `OCIOColorSpace_IN` -> `BlinkScript_OKLCHGrade` -> `OCIOColorSpace_OUT` -> `Output`

## Controls

Public controls on the gizmo:

- `input_colorspace`
- `output_colorspace`
- `l_gain`
- `l_offset`
- `c_gain`
- `c_offset`
- `hue_shift_deg`
- `mix`
- `clamp_output`
- `bypass`

## Internal working-space behavior

The Blink kernel is defined in linear-sRGB.

On init, `oklch_grade_init.py` resolves a working-space alias in this order:

1. `Utility - Linear - sRGB`
2. `lin_srgb`
3. `Linear sRGB`
4. `srgb_linear`

If none is present, the tool enters fail-safe mode (warning + bypass).

## Installation

1. Add either of these to `NUKE_PATH`:
   - `/Users/georgeantonopoulos/Dev/oklch_nuke` (recommended), or
   - `/Users/georgeantonopoulos/Dev/oklch_nuke/src`
2. Restart Nuke.
3. Nuke startup hooks used by this repo:
   - `init.py` for non-UI bootstrap (plugin paths + Python importability)
   - `menu.py` for UI registration (toolbar/menu command)
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
import oklch_grade_init
print("oklch_grade_init import: OK")
try:
    node = nuke.createNode("OKLCH_Grade", inpanel=False)
    print("OKLCH_Grade creation: OK")
    nuke.delete(node)
except Exception as exc:
    print("OKLCH_Grade creation failed:", exc)
```

If node creation fails, your `NUKE_PATH` is not pointing at the expected location or startup scripts are not being executed.

Optional override for kernel source path:

- set environment variable `OKLCH_GRADE_KERNEL_PATH` to an absolute `.cpp` path.

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
