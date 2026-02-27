# HueCorrect-Style Curve UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a HueCorrect-style curve widget to the OKLCH Grade gizmo that lets users draw per-hue corrections for Hue Shift, Chroma, and Lightness in OKLCH space.

**Architecture:** An internal `Expression` node generates a 360×1 horizontal ramp (normalized 0–1). This feeds an internal `ColorLookup` node whose RGB curves encode three OKLCH corrections. The ColorLookup output connects as a second input to the BlinkScript kernel, which samples the 1D LUT at each pixel's OKLCH hue angle using `eAccessRandom` (with bilinear filtering for smooth interpolation). The user edits curves via linked knobs on a new "Hue Curves" tab on the gizmo. Callback initialization also syncs LUT metadata (`hue_lut_width`, `hue_lut_connected`) so old scripts fail safe.

**Tech Stack:** Nuke BlinkScript (Blink C++), Nuke Python API, `.gizmo` TCL format, OKLCH color math.

---

## Architecture Detail

### Node Graph (inside gizmo group)

```
                    Expression_HueRamp (360×1, r=g=b=(x+0.5)/width)
                          │
                    ColorLookup_HueCurves
                          │
Input → OCIO_IN → BlinkScript_OKLCHGrade → OCIO_OUT → Output
                  (input 0: src)  (input 1: hueLUT)
```

### Curve Encoding

The ColorLookup node's curves map normalized hue (X: 0=0°, 1=360°) to correction values (Y):

| ColorLookup Channel | OKLCH Property | Default Y | Kernel Decoding | Effect Range |
|---------------------|----------------|-----------|-----------------|--------------|
| Red curve | Hue Shift | 0.5 | `(r - 0.5) * 360.0` | -180° to +180° |
| Green curve | Chroma Multiplier | 0.5 | `g * 2.0` | 0× to 2× |
| Blue curve | Lightness Multiplier | 0.5 | `b * 2.0` | 0× to 2× |
| Master curve | (identity, untouched) | – | – | – |

### Curve Application Order (in kernel `process()`)

1. Convert to OKLCH (existing)
2. Apply global L/C grades (existing: `l_gain`, `l_offset`, `l_contrast`, `c_gain`, `c_offset`)
3. **NEW: Apply per-hue L and C curve multipliers** (after global, multiplicative)
4. Compute hue shift (existing: global + per-band + target)
5. **NEW: Add per-hue curve hue shift** to `total_hue_shift`
6. Wrap hue, reconstruct, blend (existing)

### Enable/Disable

A `hue_curves_enable` boolean param on the kernel. When `false`, the LUT is not sampled and the curves have zero cost. The gizmo exposes this as a checkbox on the "Hue Curves" tab.

---

## Task 1: Add Internal Ramp + ColorLookup Nodes to Gizmo

**Files:**
- Modify: `src/gizmos/OKLCH_Grade.gizmo`

**Step 1: Add the Expression_HueRamp node**

Insert before the `BlinkScript_OKLCHGrade` node in the gizmo. This generates a 360×1 horizontal ramp where every pixel's RGB = its normalized X position.

```tcl
Expression {
  inputs 0
  temp_name0 norm_x
  temp_expr0 "(x + 0.5) / width"
  expr0 norm_x
  expr1 norm_x
  expr2 norm_x
  format "360 1 0 0 360 1 1 HueLUT_360x1"
  name Expression_HueRamp
  xpos -300
  ypos -260
}
```

**Step 2: Add the ColorLookup_HueCurves node**

```tcl
ColorLookup {
  inputs 1
  lut {master {}
       red {curve 0.5}
       green {curve 0.5}
       blue {curve 0.5}
       alpha {}}
  name ColorLookup_HueCurves
  xpos -300
  ypos -210
}
```

**Step 3: Connect ColorLookup as input 1 of BlinkScript**

Set `BlinkScript_OKLCHGrade` to `inputs 2`, then explicitly wire both inputs (do not rely on `inputs 2` alone):

- input 0 = `OCIOColorSpace_IN`
- input 1 = `ColorLookup_HueCurves`

Recommended verification snippet in Script Editor:

```python
g = nuke.thisNode()  # inside the group while editing the gizmo
blink = g.node("BlinkScript_OKLCHGrade")
ocio_in = g.node("OCIOColorSpace_IN")
hue_lut = g.node("ColorLookup_HueCurves")
blink.setInput(0, ocio_in)
blink.setInput(1, hue_lut)
assert blink.input(0).name() == "OCIOColorSpace_IN"
assert blink.input(1).name() == "ColorLookup_HueCurves"
```

**Step 4: Add the "Hue Curves" tab and linked knobs to the gizmo panel**

After the existing Hue group, add:

```tcl
addUserKnob {20 hue_curves_tab l "Hue Curves"}
addUserKnob {6 hue_curves_enable l "Enable Hue Curves" +STARTLINE}
addUserKnob {26 hue_curves_help l "" +STARTLINE T "<small>Draw curves to adjust Hue/Chroma/Lightness per input hue. X axis = OKLCH hue (0°–360°). Y axis = correction amount (0.5 = no change).</small>"}
addUserKnob {26 "" +STARTLINE}
addUserKnob {26 curve_mapping_label l "" +STARTLINE T "<b>Curve Mapping</b> <small>R=Hue Shift, G=Chroma Gain, B=Lightness Gain</small>"}
addUserKnob {41 hue_curves_lut l "Hue Curves" T ColorLookup_HueCurves.lut}
```

> **NOTE:** Use a single linked `lut` knob as the default implementation for reliability. Channel-specific link targets (`lut.red`, etc.) should only be attempted if confirmed in your exact Nuke build via `LookupCurves_Knob.fullyQualifiedName(channel=...)`.

**Step 5: Verify in Nuke**

Load the gizmo in Nuke. Confirm:
- The "Hue Curves" tab appears with curve editors
- Default curves are flat at y=0.5
- The internal node graph shows Expression → ColorLookup → BlinkScript input 1

**Step 6: Commit**

```bash
git add src/gizmos/OKLCH_Grade.gizmo
git commit -m "feat(gizmo): add internal Ramp + ColorLookup nodes for hue curves LUT"
```

---

## Task 2: Modify BlinkScript Kernel to Read the LUT

**Files:**
- Modify: `src/blink/oklch_grade_kernel.cpp`
- Modify: `src/gizmos/OKLCH_Grade.gizmo`

**Step 1: Add the LUT image input and enable param**

At the top of the kernel, add the second image input and new params:

```cpp
Image<eRead, eAccessPoint, eEdgeClamped> src;
Image<eRead, eAccessRandom, eEdgeClamped> hueLUT;  // NEW: 360×1 per-hue correction LUT
Image<eWrite> dst;

param:
  // ... existing params ...

  // --- Hue Curves ---
  bool hue_curves_enable;
  int hue_lut_width;      // width of LUT image (synced by callbacks)
  bool hue_lut_connected; // callbacks set true only when helper nodes are present
```

Add to `define()`:

```cpp
defineParam(hue_curves_enable, "Hue Curves Enable", false);
defineParam(hue_lut_width, "Hue LUT Width", 360);
defineParam(hue_lut_connected, "Hue LUT Connected", false);
```

**Step 2: Add a LUT sampling helper function**

```cpp
float3 sample_hue_lut(float hue_deg) {
  float w = max(float(hue_lut_width), 2.0f);
  float norm = wrap_hue_deg(hue_deg) / 360.0f;  // [0,1)
  float lut_x = norm * (w - 1.0f);
  // Use bilinear sampling for smoother response than nearest-neighbour.
  float4 lut_val = bilinear(hueLUT, lut_x + 0.5f, 0.5f);
  return float3(lut_val.x, lut_val.y, lut_val.z);
}
```

**Step 3: Apply curve corrections in `process()`**

Use two guarded applications: one in the L/C block and one in the hue-shift block.

```cpp
// --- Hue Curves: L/C multipliers ---
if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
  float3 lut = sample_hue_lut(current_lch.z);  // sample at ORIGINAL hue

  // Lightness multiplier (0.5 => 1x)
  float l_curve_mult = lut.z * 2.0f;  // Blue channel → lightness
  graded_L = graded_L * l_curve_mult;
  if (graded_L < 0.0f) graded_L = 0.0f;

  // Chroma multiplier (0.5 => 1x)
  float c_curve_mult = lut.y * 2.0f;  // Green channel → chroma
  graded_C = graded_C * c_curve_mult;
  if (graded_C < 0.0f) graded_C = 0.0f;
}

// --- Hue Curves: hue offset ---
if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
  float3 lut = sample_hue_lut(current_lch.z);
  float curve_hue_shift = (lut.x - 0.5f) * 360.0f;  // Red channel → hue shift
  total_hue_shift += curve_hue_shift * chroma_weight;
}
```

Placement requirements:
- L/C curve multipliers: after existing global L/C grading + floor clamps.
- Curve hue shift: after global/per-band/target hue accumulation and before `wrap_hue_deg`.
- Keep sampling at original hue (`current_lch.z`) to avoid feedback from already-shifted hue.

Also update the embedded Blink kernel source in `OKLCH_Grade.gizmo` (or explicitly enforce file-mode kernel loading) so the gizmo source and `src/blink/oklch_grade_kernel.cpp` cannot drift.

**Step 4: Run identity test**

With `hue_curves_enable = false`, the kernel should produce identical output to before (LUT is not sampled). With `hue_curves_enable = true` and default flat curves at 0.5, the corrections should be: hue_shift=0, chroma_mult=1, lightness_mult=1 → identity.

Verify using test vectors from `tests/oklch_reference_test_vectors.md`.

**Step 5: Commit**

```bash
git add src/blink/oklch_grade_kernel.cpp src/gizmos/OKLCH_Grade.gizmo
git commit -m "feat(kernel): add guarded hue LUT sampling with bilinear filtering and sync kernel source updates"
```

---

## Task 3: Update Callbacks to Wire New Nodes and Params

**Files:**
- Modify: `src/gizmos/oklch_grade_callbacks.py`

**Step 1: Add new params to `_PARAM_LINKS`**

```python
("hue_curves_enable", "Hue Curves Enable", "hue_curves_enable", None),
```

`hue_lut_width` and `hue_lut_connected` should be internal kernel params set directly on the Blink node (no public Link_Knob needed).

**Step 2: Add LUT metadata sync helper**

After BlinkScript recompile, set `hue_lut_width` and `hue_lut_connected` from internal node state:

```python
def _sync_hue_lut_state(node):
    blink = node.node("BlinkScript_OKLCHGrade")
    expr = node.node("Expression_HueRamp")
    lut = node.node("ColorLookup_HueCurves")
    if blink is None or expr is None:
        _set_blink_param_if_exists(blink, "hue_lut_connected", False)
        return
    width = 360
    try:
        width = max(int(expr.format().width()), 2)
    except Exception:
        pass
    _set_blink_param_if_exists(blink, "hue_lut_width", width)
    connected = bool(blink.input(1) is not None and lut is not None)
    _set_blink_param_if_exists(blink, "hue_lut_connected", connected)
```

Call this from both `initialize_this_node()` and `handle_this_knob_changed()` after link sync so script-load and delayed materialization are both covered.

Add a tiny utility used above:

```python
def _set_blink_param_if_exists(blink, internal_name, value):
    if blink is None:
        return
    knob = _knob(blink, internal_name)
    if knob is None:
        resolved = _resolve_blink_knob_name(blink, internal_name.replace("_", " ").title(), internal_name)
        knob = _knob(blink, resolved) if resolved else None
    if knob is not None:
        try:
            knob.setValue(value)
        except Exception:
            pass
```

**Step 3: Verify knob linking works end-to-end**

In Nuke, create the gizmo and confirm:
- `hue_curves_enable` checkbox toggles the kernel param
- Adjusting the curve on the "Hue Curves" tab changes the ColorLookup output
- The BlinkScript receives the LUT as input 1

**Step 4: Commit**

```bash
git add src/gizmos/oklch_grade_callbacks.py
git commit -m "feat(callbacks): wire hue curves enable param and LUT width sync"
```

---

## Task 4: Update the Gizmo Format Registration

**Files:**
- Modify: `src/gizmos/OKLCH_Grade.gizmo` (if needed)
- Modify: `src/gizmos/oklch_grade_callbacks.py` (if format registration needed)

**Step 1: Register the 360×1 format**

The Expression node references `format "360 1 0 0 360 1 1 HueLUT_360x1"`. This creates a custom format. If Nuke doesn't auto-register it from the gizmo, add to `oklch_grade_callbacks.py`:

```python
def _ensure_hue_lut_format():
    """Register 360×1 format if not already present."""
    name = "HueLUT_360x1"
    try:
        nuke.addFormat("360 1 1 " + name)
    except Exception:
        pass  # Already registered
```

Call this early in `initialize_this_node()`.

**Step 2: Verify the Expression node produces correct output**

In Nuke, check the Expression_HueRamp output:
- Pixel at x=0 should be approximately `(0.5/360, 0.5/360, 0.5/360)` ≈ 0.00139
- Pixel at x=179 should be approximately `(179.5/360, ...)` ≈ 0.49861
- Pixel at x=359 should be approximately `(359.5/360, ...)` ≈ 0.99861

**Step 3: Commit**

```bash
git add src/gizmos/oklch_grade_callbacks.py src/gizmos/OKLCH_Grade.gizmo
git commit -m "feat: register HueLUT format and verify ramp output"
```

---

## Task 5: Integration Test — Full Round-Trip with Curves

**Files:**
- Modify: `tests/oklch_reference_test_vectors.md` (add curve test vectors)

**Step 1: Test identity (curves enabled, flat at 0.5)**

1. Create OKLCH_Grade node
2. Enable "Hue Curves"
3. Leave all curves at default (flat 0.5)
4. Feed a known saturated red pixel (e.g., linear sRGB `[1, 0, 0]`)
5. Expected: output = input (within tolerance `1e-5`)

**Step 2: Test hue shift curve**

1. Pull the red curve up to ~0.75 at x≈0.08 (hue ≈29°, where linear sRGB red lands in OKLCH)
2. This encodes a hue shift of `(0.75 - 0.5) * 360 = +90°` for reds
3. Feed linear sRGB red `[1, 0, 0]` (OKLCH hue ≈ 29°)
4. Expected: hue rotates by ~+90° (red → yellow-green region)

**Step 3: Test chroma multiplier curve**

1. Reset red curve to 0.5. Pull green curve down to 0.0 at x≈0.08 (hue ≈29°, where red lives in OKLCH)
2. This encodes chroma = `0.0 * 2 = 0×` for reds → fully desaturate
3. Feed saturated red
4. Expected: output is achromatic (L preserved, C ≈ 0)

**Step 4: Test lightness multiplier curve**

1. Reset green curve. Pull blue curve down to 0.25 at x≈0.08
2. This encodes lightness = `0.25 * 2 = 0.5×` for reds → darken by half
3. Expected: output lightness ≈ 50% of original red's lightness

**Step 5: Test with curves disabled**

1. Make extreme curve adjustments (hue shift, chroma zeroed, etc.)
2. Uncheck "Enable Hue Curves"
3. Expected: output = standard OKLCH grade (curves ignored entirely)

**Step 6: Document test vectors**

Add the above test cases to `tests/oklch_reference_test_vectors.md` under a new "## Hue Curves" section with exact input values and expected output ranges.

**Step 7: Commit**

```bash
git add tests/oklch_reference_test_vectors.md
git commit -m "test: add hue curve integration test vectors"
```

---

## Task 6: Handle Edge Cases and Polish

**Files:**
- Modify: `src/blink/oklch_grade_kernel.cpp`
- Modify: `src/gizmos/OKLCH_Grade.gizmo`

**Step 1: Hue wrap at curve boundaries**

The LUT is 360 pixels wide. Hue 359° and hue 1° are adjacent on the wheel but far apart in the LUT (x=359 vs x=1). If the user creates a correction at hue 0° (x=0) and the curve drops off by x=5, there should also be a corresponding drop-off at x=355–359.

The ColorLookup node does NOT wrap automatically. Two approaches:
- **Accept the discontinuity** — document that curve edges don't wrap (simplest)
- **Add a second ColorLookup pass with offset** — overkill

Recommend: accept the discontinuity for v1 and document it in the help text. Users working near hue 0°/360° can extend their curve to both edges.

Update the help text in the gizmo:

```tcl
addUserKnob {26 hue_curves_help l "" +STARTLINE T "<small>Draw curves to adjust Hue/Chroma/Lightness per input hue. X axis = OKLCH hue (0° left → 360° right). Y = 0.5 is neutral. Note: curves do not wrap at 0°/360° — extend adjustments to both edges for hues near red.</small>"}
```

**Step 2: Add debug mode for curve LUT visualization**

Add `debug_mode == 5` to show the raw LUT values applied to each pixel:

```cpp
if (debug_mode == 5) { // Hue Curves LUT
  if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
    float3 lut = sample_hue_lut(current_lch.z);
    dst() = float4(lut.x, lut.y, lut.z, src_pixel.w);
  } else {
    dst() = float4(0.5f, 0.5f, 0.5f, src_pixel.w);
  }
  return;
}
```

Update the gizmo's debug_mode knob tooltip to include mode 5.

**Step 3: Ensure backward compatibility**

When loading an old `.nk` script that has the OKLCH_Grade gizmo without hue curve nodes:
- `hue_curves_enable` defaults to `false` → no effect
- The kernel still expects input 1, but with `inputs 1` the BlinkScript may error

This needs careful handling. If the gizmo saved before the curve feature was added, `Expression_HueRamp` and `ColorLookup_HueCurves` might not exist inside the group.

In the kernel, guard the LUT access:

```cpp
// Only sample if curves are enabled and callbacks marked LUT input valid
if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
  // ... sample and apply
}
```

In the callbacks, if helper nodes are missing:
- set `hue_lut_connected = false`
- force `hue_curves_enable` public knob to `false`
- show a status warning that curves are unavailable in this legacy instance.

**Step 4: Commit**

```bash
git add src/blink/oklch_grade_kernel.cpp src/gizmos/OKLCH_Grade.gizmo
git commit -m "feat: handle edge cases — wrap docs, debug mode 5, backward compat guard"
```

---

## Task 7: Update CLAUDE.md and Research Notes

**Files:**
- Modify: `CLAUDE.md`
- Create: `research/huecorrect_curve_architecture.md`

**Step 1: Update CLAUDE.md architecture section**

Add to the "Architecture" section:

```markdown
**Hue Curves LUT pipeline (inside gizmo group):**

\```
Expression_HueRamp (360×1) → ColorLookup_HueCurves → BlinkScript input 1
\```

`Expression_HueRamp` generates a 360×1 normalized ramp (0–1).
`ColorLookup_HueCurves` maps curves: Red=Hue Shift, Green=Chroma Mult, Blue=Lightness Mult.
The kernel samples this LUT at each pixel's OKLCH hue via `eAccessRandom`.
Default: all curves at y=0.5 (identity). Feature is gated by `hue_curves_enable` boolean.
```

**Step 2: Add research note**

Document the architecture investigation in `research/huecorrect_curve_architecture.md` for future reference (why ColorLookup+Ramp was chosen over Python baking or array params).

**Step 3: Commit**

```bash
git add CLAUDE.md research/huecorrect_curve_architecture.md
git commit -m "docs: document hue curves LUT architecture"
```

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| ColorLookup individual curve linking (`lut.red`) may not work via Link_Knob | Default to single linked `lut` knob; only use per-channel targets if verified in that Nuke build |
| BlinkScript `inputs 2` with missing input 1 on old scripts | Explicit input wiring + guard behind `hue_curves_enable && hue_lut_connected && hue_lut_width > 1` |
| LUT edge discontinuity at hue 0°/360° | Document in help text; accept for v1 |
| Kernel source drift between `.cpp` and embedded gizmo `kernelSource` | Enforce file-mode kernel loading, or keep both kernel sources updated together in same change |
| Performance: `eAccessRandom` on a second input | 360×1 image is tiny; use bilinear sampling for smoother behavior with minimal overhead |
| Nuke < 16 compatibility with second BlinkScript input | `eAccessRandom` is available in Blink API since Nuke 11+; should be safe |

## Resolved Decisions (from review)

1. **Curve UI strategy**: Use one `ColorLookup_HueCurves` with a single linked `lut` knob (R/G/B channel mapping labels in UI). Do **not** split into 3 ColorLookup nodes for v1.

2. **LUT resolution**: Keep `360` as v1 default and use bilinear sampling in kernel. Revisit `720` only if banding/stepping is observed in real shots.

3. **Interaction with existing hue controls**: Curves and existing per-band/global/target hue shifts coexist additively in v1 for backward compatibility. Re-evaluate consolidation only after usage feedback.
