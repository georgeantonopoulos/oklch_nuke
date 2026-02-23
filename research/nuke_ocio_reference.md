# Nuke OCIO Integration Reference

## Goal

Expose input/output colorspace dropdowns on the gizmo and perform accurate color conversion around the Blink OKLCH grade kernel.

Pipeline implemented:

- `Input` -> `OCIOColorSpace_IN` -> `BlinkScript_OKLCHGrade` -> `OCIOColorSpace_OUT` -> `Output`

## Dynamic colorspace menu source

Use Nuke Python API:

- `nuke.getOcioColorSpaces()`
- Returns: list of strings

Reference:
- https://learn.foundry.com/nuke/developers/140/pythonreference/_autosummary/nuke.getOcioColorSpaces.html

## OCIOColorSpace node knobs used

From the OCIOColorSpace node docs:

- `in_colorspace`: input colorspace name
- `out_colorspace`: destination colorspace name

References:
- https://learn.foundry.com/nuke/content/reference_guide/color_nodes/ociocolorspace.html

## Working-space policy

The kernel math is defined for linear-sRGB, so the gizmo resolves this internal working space via alias scan:

1. `Utility - Linear - sRGB`
2. `lin_srgb`
3. `Linear sRGB`
4. `srgb_linear`

If none is available in the active config:

- set visible warning status text
- force bypass fail-safe
- disable internal conversion/grade nodes where possible

## Why the dropdowns are Group-level

Blink kernel params are scalar controls exposed through the BlinkScript node's parameter model; colorspace selection is a graph-level OCIO concern. Therefore colorspace menus are implemented on the Group/Gizmo and synchronized to internal OCIO nodes via Python callbacks.

References:
- https://learn.foundry.com/nuke/content/reference_guide/other_nodes/blinkscript.html
- https://learn.foundry.com/nuke/developers/15.1/BlinkUserGuide/BlinkKernelAPIReference/Kernels.html
