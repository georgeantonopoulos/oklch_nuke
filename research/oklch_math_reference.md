# OKLCH Math Reference (Used by This Tool)

## Scope

This project grades in OKLCH but is fed/returned as Nuke RGB through OCIO.
The kernel path is:

1. linear-sRGB -> XYZ (D65)
2. XYZ -> OKLab
3. OKLab <-> OKLCH (polar conversion)
4. OKLab -> XYZ
5. XYZ -> linear-sRGB

Primary reference:
- https://www.w3.org/TR/css-color-4/

Context/education reference:
- https://oklch.fyi/

## Linear-sRGB <-> XYZ matrices (D65)

From CSS Color 4 (`lin_sRGB_to_XYZ` and `XYZ_to_lin_sRGB`):

### linear-sRGB -> XYZ

- X = 0.4123907992659595 R + 0.3575843393838780 G + 0.1804807884018343 B
- Y = 0.2126390058715104 R + 0.7151686787677559 G + 0.0721923153607337 B
- Z = 0.0193308187155918 R + 0.1191947797946260 G + 0.9505321522496606 B

### XYZ -> linear-sRGB

- R = 3.2409699419045213 X - 1.5373831775700935 Y - 0.4986107602930033 Z
- G = -0.9692436362808798 X + 1.8759675015077206 Y + 0.0415550574071756 Z
- B = 0.0556300796969936 X - 0.2039769588889766 Y + 1.0569715142428786 Z

Reference section:
- https://www.w3.org/TR/css-color-4/

## XYZ <-> OKLab matrices

From CSS Color 4 (`XYZ_to_OKLab`, `OKLab_to_XYZ`):

### XYZ -> LMS (pre-cube-root)

- l = 0.8190224379967030 X + 0.3619062600528904 Y - 0.1288737815209879 Z
- m = 0.0329836539323885 X + 0.9292868615863434 Y + 0.0361446663506424 Z
- s = 0.0481771893596242 X + 0.2642395317527308 Y + 0.6335478284694309 Z

### Nonlinearity

- l' = cbrt(l)
- m' = cbrt(m)
- s' = cbrt(s)

Implementation note: use a sign-preserving cube root helper for negative linear values.

### LMS' -> OKLab

- L = 0.2104542683093140 l' + 0.7936177747023054 m' - 0.0040720430116193 s'
- a = 1.9779985324311684 l' - 2.4285922420485799 m' + 0.4505937096174110 s'
- b = 0.0259040424655478 l' + 0.7827717124575296 m' - 0.8086757549230774 s'

### OKLab -> LMS'

- l' = 1.0 L + 0.3963377773761749 a + 0.2158037573099136 b
- m' = 1.0 L - 0.1055613458156586 a - 0.0638541728258133 b
- s' = 1.0 L - 0.0894841775298119 a - 1.2914855480194092 b

Then cube each channel and convert to XYZ with:

- X = 1.2268798758459243 l - 0.5578149944602171 m + 0.2813910456659647 s
- Y = -0.0405757452148008 l + 1.1122868032803170 m - 0.0717110580655164 s
- Z = -0.0763729366746601 l - 0.4214933324022432 m + 1.5869240198367816 s

Reference section:
- https://www.w3.org/TR/css-color-4/

## OKLab <-> OKLCH

Polar conversion used in the kernel:

- C = sqrt(a^2 + b^2)
- H = atan2(b, a) in degrees, wrapped to [0, 360)
- a = C cos(H)
- b = C sin(H)

For very small chroma (`C <= 0.000004`), hue is effectively undefined; implementation keeps hue stable to avoid instability.

Reference section:
- https://www.w3.org/TR/css-color-4/

## Grading operation order in this project

Given `L, C, H` from OKLCH:

- `L' = L * l_gain + l_offset`
- `C' = max(0, C * c_gain + c_offset)`
- `H' = wrap(H + hue_shift_deg)`

Then convert back to RGB and blend:

- `out = in + (graded - in) * clamp(mix, 0, 1)`

Optional output clamp:

- if `clamp_output`, clamp RGB channels to [0, 1].
