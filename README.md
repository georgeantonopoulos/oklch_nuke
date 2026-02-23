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

1. Add `/Users/georgeantonopoulos/Dev/oklch_nuke/src` to your `NUKE_PATH`.
2. Restart Nuke.
3. Nuke will execute:
   - `/Users/georgeantonopoulos/Dev/oklch_nuke/src/init.py` (startup/python bootstrap)
   - `/Users/georgeantonopoulos/Dev/oklch_nuke/src/menu.py` (UI menu/toolbar setup)
4. `menu.py` registers `/Users/georgeantonopoulos/Dev/oklch_nuke/src/nuke` and adds:
   - `Nodes > Color > OKLCH > OKLCH Grade`
   - icon: `oklch_grade.png`
5. Create `OKLCH_Grade` from that menu or tab search.

Example `NUKE_PATH` setup:

- macOS/Linux: `export NUKE_PATH=\"/Users/georgeantonopoulos/Dev/oklch_nuke/src:$NUKE_PATH\"`
- Windows: `set NUKE_PATH=C:\\path\\to\\oklch_nuke\\src;%NUKE_PATH%`

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
