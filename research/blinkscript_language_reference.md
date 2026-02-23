# BlinkScript Language Reference (Project Notes)

## Why this matters

The OKLCH grade kernel must compile in Nuke BlinkScript with valid Blink syntax, not generic C++.

## Kernel structure used

From Foundry's Blink Kernel API docs, kernels are declared with:

- `kernel Name : ImageComputationKernel<eGranularity> { ... }`
- image declarations (for example `Image<eRead, eAccessPoint, eEdgeClamped> src;` and `Image<eWrite> dst;`)
- optional `param:` section for user-facing kernel parameters
- optional `local:` section for precomputed values
- `define()` for `defineParam(...)`
- optional `init()` called once
- required `process(...)` function

Reference:
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Kernels.html

## Granularity choice

`ePixelWise` is required for OKLCH grading because each output RGB pixel depends on all RGB components, not component-isolated processing.

Reference:
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Kernels.html

## Parameter model used in this project

This kernel uses public `param:` scalars:

- `float`: `l_gain`, `l_offset`, `c_gain`, `c_offset`, `hue_shift_deg`, `mix`
- `bool`: `clamp_output`, `bypass`

These are labeled/defaulted via `defineParam(...)` in `define()`.

References:
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Kernels.html
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Types.html

## Math functions explicitly used

The kernel relies on Blink-provided math functions documented by Foundry:

- trigonometric: `sin`, `cos`, `atan2`
- power/root: `pow`, `sqrt`
- absolute/remainder/clamp: `fabs`, `fmod`, `clamp`
- **NOT available**: `smoothstep` — this is a GLSL built-in only.
  Implement manually as: `float t = clamp((x-e0)/(e1-e0), 0,1); return t*t*(3-2*t);`

Reference:
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/MathsFunctions.html

## BlinkScript node integration notes

The BlinkScript node executes a Blink kernel per output pixel and exposes kernel parameters in its UI.

Reference:
- https://learn.foundry.com/nuke/content/reference_guide/other_nodes/blinkscript.html

## Practical syntax decisions in `oklch_grade_kernel.cpp`

- Use explicit `f` float suffixes for constants.
- Use helper functions for reusable conversion blocks.
- Use `process()` with current access point reads/writes (`src()`, `dst()`) for pixel-wise operation.
- Keep alpha pass-through unchanged.
