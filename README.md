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

1. Add `src/nuke` to your Nuke plugin path.
2. Ensure `oklch_grade_init.py` is importable in Nuke's Python path.
3. Place/create `OKLCH_Grade.gizmo` in a scanned gizmo location.
4. Restart Nuke and create `OKLCH_Grade`.

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
