# Custom Hue Curve Widget — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the HueCorrect node's cluttered 9-curve UI with a single-purpose PySide2 curve widget that has a rainbow background, a single "Hue Shift" curve, and drives the existing HueCorrect node as a hidden backend to generate the 360x1 LUT consumed by the BlinkScript kernel.

**Architecture:** A `PyCustom_Knob` embeds a custom `HueCurveWidget` (QWidget subclass) in the gizmo's "Hue Curves" tab. The widget owns the curve's control points, draws a rainbow background and interactive Catmull-Rom spline, and on every edit serializes control points to HueCorrect's sat curve via `fromScript()`. HueCorrect remains in the node graph but its UI is never exposed — it purely generates the LUT image. Control point data persists via a hidden `String_Knob` (JSON). The BlinkScript kernel is completely unchanged.

**Tech Stack:** PySide2 (bundled with Nuke), Nuke Python API (`PyCustom_Knob`, `String_Knob`), HueCorrect `fromScript()` API

---

## Data Flow

```
User drags control point in HueCurveWidget
    |
    v
Python: _on_curve_changed()
    |
    v
1. Save control points JSON -> hidden hue_curve_data String_Knob
2. Evaluate spline at 37 positions -> write to HueCorrect sat curve via fromScript()
    |
    v
Nuke reprocesses: Constant -> Expression_HueRamp -> HueCorrect -> BlinkScript input 1
    |
    v
BlinkScript: sample_hue_lut_sat() reads max(R,G,B) from LUT (unchanged)
```

On panel open:
```
Nuke exec()s PyCustom_Knob command -> HueCurveWidget(nuke.thisNode())
    |
    v
updateValue(): read JSON from hue_curve_data knob -> populate _points -> repaint
```

## Key Kernel Contract (unchanged)

```cpp
// oklch_grade_kernel.cpp:147-153 — reads max(R,G,B) from 360x1 LUT
// Encoding: 1.0 = no shift, 0.0 = -180 deg, 2.0 = +180 deg
float sample_hue_lut_sat(float hue_deg) {
    float4 lut_val = bilinear(hueLUT, lut_x + 0.5f, 0.5f);
    return max(lut_val.x, max(lut_val.y, lut_val.z));
}
```

## PyCustom_Knob Constraints

- Stores a **command string** — Nuke `exec()`s it to create the widget
- **New instance** every time properties panel opens — state does NOT persist in widget
- Must implement `makeUI()` (returns self) and `updateValue()` (restores state)
- All persistent data must live in standard Nuke knobs (hidden `String_Knob`)
- `sizeHint()` override required to control widget height

---

## Tasks

### Task 1: Create the HueCurveWidget Python module

**Files:**
- Create: `src/gizmos/hue_curve_widget.py`

**Step 1: Create the widget file with full implementation**

Create `src/gizmos/hue_curve_widget.py` containing:

- `HueCurveWidget(QWidget)` — outer container with layout, Reset button, and PyCustom_Knob interface (`makeUI`, `updateValue`)
- `_HueCurveCanvas(QWidget)` — inner widget with `paintEvent` (rainbow gradient, grid, Catmull-Rom spline, control points), mouse handlers (left-click add/drag, right-click delete, double-click reset-to-1.0)
- Coordinate mapping: X axis = hue [0..1] mapping to [0..360 deg], Y axis = curve value [0..2] where 1.0 = identity
- `_RAINBOW_STOPS` — approximate OKLCH hue colors at ~30-degree intervals for the gradient background
- `_evaluate_curve(x)` — Catmull-Rom interpolation through control points with mirrored tangents at endpoints
- `_save_points_to_knob()` / `_load_points_from_knob()` — JSON serialization to hidden `hue_curve_data` String_Knob
- `_push_curve_to_huecorrect()` — evaluates spline at 37 positions (every 10 deg), builds TCL string, calls `HueCorrect_HueCurves.hue.fromScript()`
- `create_widget(node)` — factory function for PyCustom_Knob command string, returns `_FallbackWidget` in non-GUI sessions
- Endpoint locking: first point locked at x=0, last at x=1, Y values kept in sync (hue wraps)

HueCorrect sat curve TCL format:
```
{sat {curve x0.000000 1.000000 x0.027778 1.003000 ...} lum {} red {} green {} blue {} r_sup {} g_sup {} b_sup {} sat_thrsh {}}
```

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('src/gizmos/hue_curve_widget.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/gizmos/hue_curve_widget.py
git commit -m "feat(hue-curves): add PySide2 HueCurveWidget with rainbow background and Catmull-Rom spline"
```

---

### Task 2: Update the gizmo to use PyCustom_Knob

**Files:**
- Modify: `src/gizmos/OKLCH_Grade.gizmo` (lines 43-46)

**Step 1: Replace HueCorrect knob exposure with PyCustom_Knob**

Replace lines 43-46 (the hue_curves_tab section):

OLD:
```
 addUserKnob {20 hue_curves_tab l "Hue Curves"}
 addUserKnob {41 hue_curves_enable l "Enable Hue Curves" T "BlinkScript_OKLCHGrade.hue_curves_enable"}
 addUserKnob {26 hue_curves_help l "" +STARTLINE T "<small>Use the <b>sat</b> curve to shift hue per input hue. Y=1 is neutral. Y&gt;1 shifts hue positive, Y&lt;1 shifts negative. Range 0-2 maps to -180 to +180 degrees. Other curves are unused. Note: rainbow shows approximate HSV hues.</small>"}
 addUserKnob {41 hue_curves_lut l "Hue Curves" T HueCorrect_HueCurves.hue}
```

NEW:
```
 addUserKnob {20 hue_curves_tab l "Hue Curves"}
 addUserKnob {41 hue_curves_enable l "Enable Hue Curves" T "BlinkScript_OKLCHGrade.hue_curves_enable"}
 addUserKnob {26 hue_curves_help l "" +STARTLINE T "<small>Drag points to shift hue. Y=0 is identity. Left-click adds, right-click removes. Endpoints linked (hue wraps). Range: -180 to +180 degrees.</small>"}
 addUserKnob {1 hue_curve_data l "" +INVISIBLE T ""}
 addUserKnob {12 hue_curve_widget l "" +STARTLINE T "hue_curve_widget.create_widget(nuke.thisNode())"}
```

Knob type 12 = `PyCustom_Knob`. The hidden `hue_curve_data` (type 1 = `String_Knob`) stores JSON.

**Step 2: Verify gizmo loads**

In Nuke Script Editor:
```python
node = nuke.createNode("OKLCH_Grade", inpanel=True)
```
Expected: "Hue Curves" tab shows the custom widget (or at minimum no crash).

**Step 3: Commit**

```bash
git add src/gizmos/OKLCH_Grade.gizmo
git commit -m "feat(hue-curves): replace HueCorrect UI exposure with PyCustom_Knob widget"
```

---

### Task 3: Ensure module import path

**Files:**
- Read: `src/init.py` (verify `src/gizmos/` is on `sys.path`)
- Possibly modify: `src/init.py`

**Step 1: Check existing path setup**

Read `src/init.py`. The `hue_curve_widget` module lives in `src/gizmos/`. Verify this directory is added to `sys.path`. If not, add:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gizmos"))
```

**Step 2: Test import**

```python
import hue_curve_widget
print(hue_curve_widget.create_widget)
```
Expected: `<function create_widget at 0x...>`

**Step 3: Commit if changes were needed**

---

### Task 4: Update callbacks for default curve data

**Files:**
- Modify: `src/gizmos/oklch_grade_callbacks.py` (function `_sync_hue_lut_state`)

**Step 1: Add default curve data initialization**

In `_sync_hue_lut_state`, after existing code, add logic to populate `hue_curve_data` with default JSON `[[0.0, 1.0], [1.0, 1.0]]` if it's empty. This ensures new node instances have valid data.

```python
    curve_data_knob = _knob(node, "hue_curve_data")
    if curve_data_knob is not None:
        try:
            raw = curve_data_knob.value()
            if not raw or not raw.strip():
                import json
                curve_data_knob.setValue(json.dumps([[0.0, 1.0], [1.0, 1.0]]))
        except Exception:
            pass
```

**Step 2: Test**

```python
node = nuke.createNode("OKLCH_Grade", inpanel=False)
print(node.knob("hue_curve_data").value())
nuke.delete(node)
```
Expected: `[[0.0, 1.0], [1.0, 1.0]]`

**Step 3: Commit**

```bash
git add src/gizmos/oklch_grade_callbacks.py
git commit -m "fix: initialize default hue curve data on new node creation"
```

---

### Task 5: Integration test — HueCorrect write-back

**Files:** None (manual test)

**Step 1: Test the widget-to-HueCorrect data flow**

```python
import json
node = nuke.toNode("OKLCH_Grade1")

# Set test curve with bump at cyan (0.5 = 180 deg)
test_points = [[0.0, 1.0], [0.25, 1.0], [0.5, 1.5], [0.75, 1.0], [1.0, 1.0]]
node.knob("hue_curve_data").setValue(json.dumps(test_points))

from hue_curve_widget import HueCurveWidget
w = HueCurveWidget(node)
w.updateValue()
w._push_curve_to_huecorrect()

# Verify HueCorrect was updated
hc = node.node("HueCorrect_HueCurves")
script = hc.knob("hue").toScript()
assert "1.500000" in script, f"Expected 1.5 in sat curve, got: {script[:300]}"
print("PASS: HueCorrect sat curve updated correctly")
```

**Step 2: Visual verification**

Enable hue curves, set debug_mode=5. Viewport should show non-uniform grayscale matching the curve (brighter at 180-deg hues).

**Step 3: If `fromScript()` format is wrong**

If Nuke rejects the TCL format, fall back to using the animation curve API:
```python
hue_knob = hc.knob("hue")
# Access the sat curve (index 0) and set keys directly
```
This is a backup plan documented here in case the TCL approach fails.

---

### Task 6: Scene save/load persistence test

**Files:** None (manual test)

**Step 1: Test round-trip persistence**

1. Create OKLCH_Grade, add curve points via the widget
2. Save: `nuke.scriptSave("/tmp/oklch_test.nk")`
3. Clear: `nuke.scriptClear()`
4. Load: `nuke.scriptOpen("/tmp/oklch_test.nk")`
5. Verify: `print(nuke.toNode("OKLCH_Grade1").knob("hue_curve_data").value())`

Expected: JSON matches what was set before save.

**Step 2: Verify widget restores visually**

Open the node's Hue Curves tab. The curve should show the same control points as before save.

---

### Task 7: Clean up help text and Y-axis labels

**Files:**
- Modify: `src/gizmos/hue_curve_widget.py` (paintEvent Y-axis labels)

**Step 1: Verify Y-axis shows degree labels**

The Y axis should show: -180, -90, 0, +90, +180 (mapping from curve values 0, 0.5, 1.0, 1.5, 2.0). Confirm this is correct in the `paintEvent` grid drawing code.

**Step 2: Add tooltip**

Add `self.setToolTip("Left-click: add/drag point | Right-click: remove point | Double-click: reset to zero")` in `__init__`.

**Step 3: Commit**

```bash
git add src/gizmos/hue_curve_widget.py
git commit -m "polish: Y-axis degree labels and tooltip for hue curve widget"
```

---

## Risk Notes

1. **HueCorrect `fromScript` format** — The sat curve TCL format must be exact. Test early in Task 5. Fallback: use animation curve key-setting API.

2. **PyCustom_Knob type 12 in `.gizmo` files** — Less commonly tested than via `addKnob()`. If gizmo parser rejects it, move knob creation to `initialize_this_node()` in callbacks.

3. **Widget height collapse** — PyCustom_Knob widgets sometimes get zero height. Mitigations: `sizeHint()`, `setMinimumHeight(200)`, `setFixedHeight()`.

4. **Catmull-Rom overshoot** — Extreme control points can produce values outside [0, 2]. Clamp in `_push_curve_to_huecorrect()` (already planned). Consider visual clamping too.

5. **Non-GUI sessions** — Render farms run Nuke in `-t` mode with no Qt. The `create_widget()` factory returns a no-op `_FallbackWidget`. HueCorrect still has its last-saved curve data, so renders work fine — only the interactive widget is missing.
