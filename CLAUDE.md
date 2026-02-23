# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Nuke gizmo + BlinkScript kernel that grades footage in OKLCH colorspace while converting from/to arbitrary OCIO colorspaces. The kernel lives entirely in `src/blink/oklch_grade_kernel.cpp` (standard C++ compiled at runtime by Nuke's BlinkScript engine).

## Installation / testing

There is no build step. To test changes, load Nuke with `NUKE_PATH` pointing at the repo root:

```sh
export NUKE_PATH="/Users/georgeantonopoulos/Dev/oklch_nuke:$NUKE_PATH"
```

Then validate in Nuke's Script Editor using the diagnostic snippet and manual test vectors in `tests/oklch_reference_test_vectors.md`:

```python
import oklch_grade_init
node = nuke.createNode("OKLCH_Grade", inpanel=False)
# run checks from tests/oklch_reference_test_vectors.md
nuke.delete(node)
```

Identity round-trip tolerance: `max_abs_err <= 1e-5`. Alpha must pass through unchanged exactly.

Override the kernel path without touching the gizmo:

```sh
export OKLCH_GRADE_KERNEL_PATH="/path/to/oklch_grade_kernel.cpp"
```

## Architecture

**Data pipeline inside the gizmo group:**

```
Input → OCIOColorSpace_IN → BlinkScript_OKLCHGrade → OCIOColorSpace_OUT → Output
```

`OCIOColorSpace_IN` converts from `input_colorspace` → `lin_srgb` (working space).
`BlinkScript_OKLCHGrade` runs the Blink kernel entirely in linear-sRGB.
`OCIOColorSpace_OUT` converts from `lin_srgb` → `output_colorspace`.

**Startup sequence (two supported install layouts):**

| File | Purpose |
|------|---------|
| `init.py` / `menu.py` (repo root) | Used when `NUKE_PATH` points at repo root; forward-delegates to `src/` |
| `src/init.py` | Registers `src/gizmos/` on `nuke.pluginPath()` and `sys.path` |
| `src/menu.py` | Registers `Nodes > Color > OKLCH > OKLCH Grade` toolbar entry (UI sessions only) |
| `src/gizmos/oklch_grade_init.py` | Gizmo Python callbacks: OCIO menu population, linear-sRGB alias detection, knob↔internal-node sync, kernel loading |
| `src/blink/oklch_grade_kernel.cpp` | Full OKLCH math (linear-sRGB ↔ XYZ ↔ OKLab ↔ OKLCH) and grade controls |
| `src/gizmos/OKLCH_Grade.gizmo` | Group node definition with public knobs |

**Kernel load path resolution** (in `oklch_grade_init._find_kernel_path`):
1. `$OKLCH_GRADE_KERNEL_PATH` env var (absolute path)
2. Relative: `../blink/oklch_grade_kernel.cpp` from `oklch_grade_init.py`'s directory

**Working-space detection** (`detect_linear_srgb_space`): tries these aliases in order against the active OCIO config:
1. `Utility - Linear - sRGB`
2. `lin_srgb`
3. `Linear sRGB`
4. `srgb_linear`

If none match, the gizmo enters fail-safe: both OCIO nodes disabled, `bypass` forced `True`, status knob shows a warning.

## Key implementation notes

- **BlinkScript constraints**: the kernel is `ePixelWise` — no neighbourhood access. No standard library. `signed_cbrt` is hand-rolled because BlinkScript's `pow` cannot take a negative base.
- **Hue wrap**: `wrap_hue_deg` uses `fmod` (not `floor`, which is absent from BlinkScript's math surface). Handles negative remainder with an `if (wrapped < 0) wrapped += 360` guard.
- **Chroma floor**: negative chroma after `c_offset` is hard-clamped to `0.0` before converting back, preventing imaginary colors.
- **Alpha**: passed through unchanged (`dst() = float4(..., rgba.w)`). Grade math never touches channel 3.
- **Menu guard**: `menu.py` uses `_oklch_grade_menu_registered` attribute on the `nuke` module to prevent duplicate toolbar entries on re-import.
- **`SYNC_KNOBS`**: set defined in `oklch_grade_init.py`; only knobs in this set trigger `_sync_internal_nodes` in `handle_knob_changed`.

## Research references

`research/` contains source-backed notes (not generated). Do not treat them as normative specs — prefer the CSS Color 4 spec and Björn Ottosson's OKLab article for authoritative constants.
