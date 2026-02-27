# HueCorrect Curve Architecture for OKLCH Grade

## Summary

This document records the chosen v1 architecture for per-hue curve grading in `OKLCH_Grade`.

Pipeline:

1. `Expression_HueRamp` creates a `360x1` horizontal ramp with RGB values `(x + 0.5) / width`.
2. `ColorLookup_HueCurves` remaps that ramp through user-editable RGB curves.
3. `BlinkScript_OKLCHGrade` samples the LUT by pixel hue and applies:
   - `R`: additive hue shift encoding (`(r - 0.5) * 360`)
   - `G`: chroma multiplier encoding (`g * 2`)
   - `B`: lightness multiplier encoding (`b * 2`)

## Why this architecture

- Uses native Nuke curve UI (`ColorLookup`) with minimal custom UI code.
- Keeps per-pixel math in Blink where OKLCH conversion already exists.
- Avoids large serialized array knobs and Python-side LUT baking complexity.
- Small LUT footprint (`360x1`) keeps runtime overhead low.

## Key implementation details

- Kernel uses a second image input (`hueLUT`) with `eAccessRandom`.
- Sampling uses bilinear filtering for smoother transitions at `360` resolution.
- Curves are gated by `hue_curves_enable`.
- Additional guards (`hue_lut_connected`, `hue_lut_width > 1`) prevent accidental LUT reads on legacy or partially wired nodes.

## UI mapping

- Public UI presents a single linked `ColorLookup_HueCurves.lut` editor.
- Channel mapping is documented in-panel:
  - Red curve: Hue Shift
  - Green curve: Chroma Gain
  - Blue curve: Lightness Gain

This avoids fragile per-channel link targets (`lut.red`, etc.) across Nuke versions.

## Edge cases and v1 decisions

- Curve seam at `0/360` does not wrap automatically in `ColorLookup`.
  - v1 decision: document this behavior and ask users to paint both edges for red-adjacent ranges.
- Existing per-band hue controls and curve hue controls coexist additively.
  - v1 decision: preserve backward compatibility; evaluate simplification after usage feedback.

## Validation checklist

- Fresh-load gizmo creation in a new Nuke session.
- Confirm Blink input wiring:
  - input 0 = `OCIOColorSpace_IN`
  - input 1 = `ColorLookup_HueCurves`
- Confirm identity:
  - `hue_curves_enable = false` => baseline output unchanged.
  - `hue_curves_enable = true`, flat curves at `0.5` => identity output.
- Confirm debug mode `5` visualizes sampled LUT values.
