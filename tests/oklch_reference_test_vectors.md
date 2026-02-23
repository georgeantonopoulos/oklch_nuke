# OKLCH Grade Reference Test Vectors

These vectors are intended for manual or scripted validation inside Nuke after loading `OKLCH_Grade.gizmo`.

## Default knobs for identity

- `l_gain = 1`
- `l_offset = 0`
- `c_gain = 1`
- `c_offset = 0`
- `hue_shift_deg = 0`
- `mix = 1`
- `clamp_output = false`
- `bypass = false`

Expected: output matches input within `max_abs_err <= 1e-5` for RGB, alpha unchanged exactly.

## Input vectors (linear domain)

Use these RGBA values:

1. `(-0.5, -0.1, 0.0, 1.0)`
2. `(0.0, 0.0, 0.0, 1.0)`
3. `(0.18, 0.18, 0.18, 1.0)`
4. `(1.0, 1.0, 1.0, 1.0)`
5. `(2.0, 1.0, 0.25, 1.0)`
6. `(4.0, 0.5, -0.2, 0.5)`

## Scenario checks

### 1) Identity round-trip

- Use default knobs.
- Verify RGB epsilon <= `1e-5` and alpha identical.

### 2) Achromatic stability near C ~ 0

- Input: `(0.18, 0.18, 0.18, 1.0)`
- Set `hue_shift_deg = 180`.
- Expected: output remains visually neutral (no chroma spike).

### 3) Hue wrap behavior

- Input: `(1.0, 0.25, 0.1, 1.0)`
- Compare `hue_shift_deg = 450` with `hue_shift_deg = 90`.
- Expected: outputs are equivalent within float tolerance.

### 4) Chroma floor

- Input: `(0.3, 0.2, 0.1, 1.0)`
- Set `c_gain = 1`, `c_offset = -10`.
- Expected: chroma clamps at zero internally; no NaNs/Infs.

### 5) Clamp policy

- Input: `(4.0, 0.5, -0.2, 1.0)`
- Set strong grade (e.g. `l_gain = 2`, `c_gain = 2`).
- `clamp_output = false`: out-of-range values allowed.
- `clamp_output = true`: RGB bounded to [0,1].

### 6) Mix behavior

- Any non-trivial grade.
- `mix = 0`: output equals input.
- `mix = 1`: output equals fully graded result.

### 7) Alpha integrity

- Any vector with alpha != 1 (e.g. `(0.2, 0.3, 0.4, 0.37)`).
- Expected: output alpha remains `0.37` exactly.

### 8) Missing linear-sRGB alias fail-safe

- Run with OCIO config lacking listed aliases.
- Expected: warning status text shown; bypass enabled fail-safe.
