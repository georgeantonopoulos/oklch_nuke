# Colorpicker -> Hue Target (deg) Investigation

## Goal

Add a gizmo color-pick workflow that sets `hue_target_deg` to the same hue basis used by the Blink kernel, so picker-driven targeting is numerically correct.

## Current State (Repo)

- `src/gizmos/OKLCH_Grade.gizmo` currently wraps the Blink node with:
  - `OCIOColorSpace_IN: scene_linear -> color_picking`
  - `OCIOColorSpace_OUT: color_picking -> scene_linear`
- `src/blink/oklch_grade_kernel.cpp` computes hue using fixed **linear-sRGB -> XYZ -> OKLab -> OKLCH** math constants.

This means correctness depends on `color_picking` being linear-sRGB, which is not guaranteed in OCIO configs.

## Why Picker Hue Can Be Wrong

`color_picking` is an OCIO **role**, defined as the colorspace for color-picking operations, not necessarily linear-sRGB. If picker values are interpreted as linear-sRGB without conversion, hue angle can drift from the intended target.

## Research Findings

1. OCIO role semantics:
`color_picking` is a role-level colorspace choice, not a fixed standard space.
Source: <https://opencolorio.readthedocs.io/en/latest/guides/authoring/colorspaces.html#roles>

2. Nuke sampling API:
Prefer `Node.sample(chan, x, y, dx, dy)` for deterministic pixel sampling from a specific node output.
`nuke.sample(...)` is deprecated.
Source: <https://learn.foundry.com/nuke/developers/140/pythonreference/_autosummary/nuke.Node.html>

3. Viewer sampling behavior:
Nuke viewer color sampling can be done from the viewed result or from source image input (`Ctrl+Alt` mode).
Source: <https://learn.foundry.com/nuke/content/getting_started/using_interface/working_viewer.html>

## Recommended Implementation

### 1) Make kernel working space explicit

Use the detected linear-sRGB alias for the internal bridge:

- `OCIOColorSpace_IN.out_colorspace = working_linear_srgb_space`
- `OCIOColorSpace_OUT.in_colorspace = working_linear_srgb_space`

Keep public input/output menus as external IO only.

This aligns kernel assumptions with actual pixel data.

### 2) Add a dedicated hue-pick action in the Gizmo UI

Add knobs:

- `pick_hue_target_from_viewer` (PyScript button)
- optional readout: `picked_hue_deg`, `picked_chroma`

Button behavior:

1. Resolve active viewer + pick position (or sample bbox center).
2. Sample RGB from `OCIOColorSpace_IN` output using `Node.sample`.
3. Convert sampled linear-sRGB to OKLCH hue using the same math constants as the kernel.
4. If chroma is below epsilon, do not overwrite target; show status ("picked pixel near-neutral; hue undefined").
5. Else set `hue_target_deg = wrap(h)`.

### 3) Keep eyedropper path as optional fallback

If you want direct eyedropper UX on a color knob, convert from picker space to working linear-sRGB before OKLCH conversion. Do not assume picker value is linear-sRGB.

## Conversion Guardrails

- Reuse exact matrix constants from `src/blink/oklch_grade_kernel.cpp` to avoid drift.
- Use sign-preserving cube root for negative linear values.
- Wrap hue to `[0, 360)`.
- Treat very small chroma as undefined hue (`C <= 4e-6` parity with kernel).

## Suggested File Touchpoints

- `src/gizmos/OKLCH_Grade.gizmo`
  - add pick button/readout knobs
  - fix internal OCIO bridge defaults to working linear-sRGB
- `src/gizmos/oklch_grade_callbacks.py`
  - implement pick callback + conversion helpers
  - status messaging for low-chroma picks
- `tests/oklch_reference_test_vectors.md`
  - add picker conversion vectors:
    - saturated primaries/secondaries
    - near-neutral guard behavior
    - hue wrap around 0/360 boundary

## Validation Checklist

1. Pick saturated red patch -> `hue_target_deg` near expected red anchor (wrap-safe around 0/360).
2. Pick cyan/blue/magenta patches -> target tracks expected sector.
3. Pick neutral gray -> target not overwritten; status warns hue undefined.
4. Change OCIO config with different `color_picking` role -> picker still matches kernel hue after explicit conversion.
