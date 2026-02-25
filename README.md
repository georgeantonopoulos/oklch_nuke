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

The gizmo stores baked Blink metadata (`isBaked true`) while keeping the inline `kernelSource` embedded in the node.
Menu scripts only register plugin paths and add the gizmo creation command.

## Installation

There are two ways to install this gizmo.

### Option A: `init.py` (Recommended)

1. Clone or download this repository.
2. In your `~/.nuke/init.py` file, add the following line:

   ```python
   nuke.pluginAddPath('/path/to/oklch_nuke')
   ```

   *(Ensure you replace `/path/to/oklch_nuke` with the actual path to the cloned repository)*
3. Restart Nuke.

### Option B: `NUKE_PATH` Environment Variable

1. Clone or download this repository.
2. Add the repository folder to your `NUKE_PATH` environment variable.
   - **macOS/Linux**: `export NUKE_PATH="/path/to/oklch_nuke:$NUKE_PATH"`
   - **Windows**: `set NUKE_PATH=C:\path\to\oklch_nuke;%NUKE_PATH%`
3. Restart Nuke.

### Verification

Once installed and Nuke is restarted, you can access the tool from the Nuke toolbar at:
`Nodes > Color > OKLCH > OKLCH Grade`
*(Icon: `oklch_grade.png`)*

You can also create the node using the standard Nuke node search (Tab) and typing `OKLCH_Grade`.

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
