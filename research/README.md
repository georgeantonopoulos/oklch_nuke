# Research Pack

This folder captures the references used to design the `OKLCH_Grade` Nuke tool and Blink kernel.

## Contents

- `blinkscript_language_reference.md`
  - Blink kernel structure, parameter model, and math functions used by the kernel.
- `oklch_math_reference.md`
  - OKLab/OKLCH conversion path and exact constants used in `src/blink/oklch_grade_kernel.cpp`.
- `nuke_ocio_reference.md`
  - Nuke OCIO integration details for dynamic input/output colorspace menus.

## Primary Sources

1. [oklch.fyi](https://oklch.fyi/)
2. [Nuke BlinkScript node reference](https://learn.foundry.com/nuke/content/reference_guide/other_nodes/blinkscript.html)
3. [Blink Kernel API Reference (Kernels)](https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Kernels.html)
4. [Blink mathematical functions (requested URL)](https://learn.foundry.com/nuke/developers/16.0/BlinkReferenceGuide/MathematicalFunctions/)
5. [Blink mathematical functions (resolved active docs URL)](https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/MathsFunctions.html)
6. [Nuke Python `nuke.getOcioColorSpaces()`](https://learn.foundry.com/nuke/developers/140/pythonreference/_autosummary/nuke.getOcioColorSpaces.html)
7. [CSS Color 4: OKLab/OKLCH conversion algorithms](https://www.w3.org/TR/css-color-4/)
8. [Nuke OCIOColorSpace node reference](https://learn.foundry.com/nuke/content/reference_guide/color_nodes/ociocolorspace.html)

## Notes

- The implementation intentionally uses the CSS Color 4 OKLab matrices and conversion sequence to avoid ad-hoc matrix variants.
- The gizmo-level input/output colorspace dropdowns are populated from the active OCIO config using `nuke.getOcioColorSpaces()`.
- The internal grading working space is linear-sRGB, with fail-safe bypass if no known linear-sRGB alias exists in the config.
