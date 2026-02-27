kernel OKLCHGrade : ImageComputationKernel<ePixelWise> {
  Image<eRead, eAccessPoint, eEdgeClamped> src;
  Image<eRead, eAccessRandom, eEdgeClamped> hueLUT;
  Image<eWrite> dst;

param:
  // --- Lightness ---
  float l_gain;
  float l_offset;
  float l_contrast;
  float l_pivot;

  // --- Chroma ---
  float c_gain;
  float c_offset;

  // --- Global Hue ---
  // Shifts ALL hues by a constant offset in degrees.
  // The effect fades to zero for near-achromatic pixels (Chroma <
  // hue_chroma_threshold), preventing muddy grey casts when rotating hue
  // globally.
  float hue_shift_deg;
  float hue_chroma_threshold; // Chroma below which the global+band shifts fade
                              // out (0..0.2)

  // --- Hue Band Selectors ---
  // Each shifts only the pixels whose original hue falls within that colour
  // band. Influence falls off smoothly away from each band centre using a
  // cosine window (half-angle = 60 deg), so adjacent bands overlap and blend
  // naturally like a colour wheel divided into six 60-degree sectors.
  //
  //  Band centres (OKLCH hue wheel, perceptually placed):
  //    Red     ~  0 / 360 deg
  //    Yellow  ~ 85 deg
  //    Green   ~ 145 deg
  //    Cyan    ~ 195 deg
  //    Blue    ~ 265 deg
  //    Magenta ~ 325 deg
  float hue_shift_red;
  float hue_shift_yellow;
  float hue_shift_green;
  float hue_shift_cyan;
  float hue_shift_blue;
  float hue_shift_magenta;

  // --- Target Hue Correction ---
  float hue_target_deg;
  float hue_target_shift;
  float hue_target_falloff_deg;

  // --- Utilities ---
  float mix;
  bool clamp_output;
  bool bypass;
  int debug_mode;

  // --- Hue Curves ---
  bool hue_curves_enable;
  int hue_lut_width;
  bool hue_lut_connected;

  void define() {
    defineParam(l_gain, "L Gain", 1.0f);
    defineParam(l_offset, "L Offset", 0.0f);
    defineParam(l_contrast, "L Contrast", 1.0f);
    defineParam(l_pivot, "L Pivot", 0.18f);
    defineParam(c_gain, "C Gain", 1.0f);
    defineParam(c_offset, "C Offset", 0.0f);

    defineParam(hue_shift_deg, "Hue Shift (deg)", 0.0f);
    defineParam(hue_chroma_threshold, "Hue Chroma Threshold", 0.05f);

    defineParam(hue_shift_red, "Hue Shift Red", 0.0f);
    defineParam(hue_shift_yellow, "Hue Shift Yellow", 0.0f);
    defineParam(hue_shift_green, "Hue Shift Green", 0.0f);
    defineParam(hue_shift_cyan, "Hue Shift Cyan", 0.0f);
    defineParam(hue_shift_blue, "Hue Shift Blue", 0.0f);
    defineParam(hue_shift_magenta, "Hue Shift Magenta", 0.0f);

    defineParam(hue_target_deg, "Hue Target (deg)", 0.0f);
    defineParam(hue_target_shift, "Hue Target Shift", 0.0f);
    defineParam(hue_target_falloff_deg, "Hue Target Falloff", 25.0f);

    defineParam(mix, "Mix", 1.0f);
    defineParam(clamp_output, "Clamp Output", false);
    defineParam(bypass, "Bypass", false);
    defineParam(debug_mode, "Debug Mode", 0);

    defineParam(hue_curves_enable, "Hue Curves Enable", false);
    defineParam(hue_lut_width, "Hue LUT Width", 360);
    defineParam(hue_lut_connected, "Hue LUT Connected", false);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  float signed_cbrt(float x) {
    if (x == 0.0f)
      return 0.0f;
    return (x > 0.0f) ? pow(x, 1.0f / 3.0f) : -pow(-x, 1.0f / 3.0f);
  }

  float clamp01(float x) { return clamp(x, 0.0f, 1.0f); }

  // Smoothstep is not a Blink built-in (it is GLSL-only).
  // This replicates the standard cubic Hermite polynomial: 3t^2 - 2t^3
  float smooth_ramp(float edge0, float edge1, float x) {
    float t = clamp((x - edge0) / (edge1 - edge0), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
  }

  float wrap_hue_deg(float h) {
    float wrapped = h - 360.0f * floor(h / 360.0f);
    return (wrapped < 0.0f) ? wrapped + 360.0f : wrapped;
  }

  // Shortest angular distance from angle a to angle b, in degrees.
  // Returns a value in [-180, 180].
  float hue_delta(float a, float b) {
    float d = wrap_hue_deg(b) - wrap_hue_deg(a);
    if (d > 180.0f)
      d -= 360.0f;
    if (d < -180.0f)
      d += 360.0f;
    return d;
  }

  // Cosine-window hue band weight.
  // Returns 1 at centre_deg, 0 at +/-half_width_deg, smooth in between.
  // Clamped to [0,1] so it never goes negative at the edges.
  float hue_band_weight(float current_hue, float centre_deg,
                        float half_width_deg) {
    float delta = hue_delta(current_hue, centre_deg);
    float norm = delta / half_width_deg; // -1 to 1 at the edges
    if (norm < -1.0f || norm > 1.0f)
      return 0.0f;
    // cos(pi * norm): 1 at centre, 0 at edges, smooth cosine falloff
    float pi = 3.1415926536f;
    return 0.5f * (1.0f + cos(pi * norm));
  }

  float3 sample_hue_lut(float hue_deg) {
    float w = max(float(hue_lut_width), 2.0f);
    float norm = wrap_hue_deg(hue_deg) / 360.0f;
    float lut_x = norm * (w - 1.0f);
    float4 lut_val = bilinear(hueLUT, lut_x + 0.5f, 0.5f);
    return float3(lut_val.x, lut_val.y, lut_val.z);
  }

  // ---------------------------------------------------------------------------
  // Colour space conversion matrices
  // ---------------------------------------------------------------------------

  float3 linear_srgb_to_xyz(float3 rgb) {
    // CSS Color 4: lin_sRGB_to_XYZ (D65)
    float x = 0.4123907992659595f * rgb.x + 0.3575843393838780f * rgb.y +
              0.1804807884018343f * rgb.z;
    float y = 0.2126390058715104f * rgb.x + 0.7151686787677559f * rgb.y +
              0.0721923153607337f * rgb.z;
    float z = 0.0193308187155918f * rgb.x + 0.1191947797946260f * rgb.y +
              0.9505321522496606f * rgb.z;
    return float3(x, y, z);
  }

  float3 xyz_to_linear_srgb(float3 xyz) {
    // CSS Color 4: XYZ_to_lin_sRGB
    float r = 3.2409699419045213f * xyz.x + -1.5373831775700935f * xyz.y +
              -0.4986107602930033f * xyz.z;
    float g = -0.9692436362808798f * xyz.x + 1.8759675015077206f * xyz.y +
              0.0415550574071756f * xyz.z;
    float b = 0.0556300796969936f * xyz.x + -0.2039769588889766f * xyz.y +
              1.0569715142428786f * xyz.z;
    return float3(r, g, b);
  }

  float3 xyz_to_oklab(float3 xyz) {
    // CSS Color 4: XYZ_to_OKLab
    float l = 0.8190224379967030f * xyz.x + 0.3619062600528904f * xyz.y +
              -0.1288737815209879f * xyz.z;
    float m = 0.0329836539323885f * xyz.x + 0.9292868615863434f * xyz.y +
              0.0361446663506424f * xyz.z;
    float s = 0.0481771893596242f * xyz.x + 0.2642395317527308f * xyz.y +
              0.6335478284694309f * xyz.z;

    float l_ = signed_cbrt(l);
    float m_ = signed_cbrt(m);
    float s_ = signed_cbrt(s);

    float L = 0.2104542683093140f * l_ + 0.7936177747023054f * m_ +
              -0.0040720430116193f * s_;
    float a = 1.9779985324311684f * l_ + -2.4285922420485799f * m_ +
              0.4505937096174110f * s_;
    float b = 0.0259040424655478f * l_ + 0.7827717124575296f * m_ +
              -0.8086757549230774f * s_;

    return float3(L, a, b);
  }

  float3 oklab_to_xyz(float3 lab) {
    // CSS Color 4: OKLab_to_XYZ
    float l_ = 1.0f * lab.x + 0.3963377773761749f * lab.y +
               0.2158037573099136f * lab.z;
    float m_ = 1.0f * lab.x + -0.1055613458156586f * lab.y +
               -0.0638541728258133f * lab.z;
    float s_ = 1.0f * lab.x + -0.0894841775298119f * lab.y +
               -1.2914855480194092f * lab.z;

    float l = l_ * l_ * l_;
    float m = m_ * m_ * m_;
    float s = s_ * s_ * s_;

    float x = 1.2268798758459243f * l + -0.5578149944602171f * m +
              0.2813910456659647f * s;
    float y = -0.0405757452148008f * l + 1.1122868032803170f * m +
              -0.0717110580655164f * s;
    float z = -0.0763729366746601f * l + -0.4214933324022432f * m +
              1.5869240198367816f * s;

    return float3(x, y, z);
  }

  float3 oklab_to_oklch(float3 lab) {
    float c = sqrt((lab.y * lab.y) + (lab.z * lab.z));
    float h = atan2(lab.z, lab.y) * 57.2957795131f;

    if (h < 0.0f) {
      h += 360.0f;
    }

    if (c <= 0.000004f) {
      h = 0.0f;
    }

    return float3(lab.x, c, h);
  }

  float3 oklch_to_oklab(float3 lch) {
    float rad = lch.z * (3.1415926536f / 180.0f);
    float a = lch.y * cos(rad);
    float b = lch.y * sin(rad);
    return float3(lch.x, a, b);
  }

  // ---------------------------------------------------------------------------
  // Process
  // ---------------------------------------------------------------------------

  void process() {
    float4 src_pixel = src();
    float3 in_rgb = float3(max(0.0f, src_pixel.x), max(0.0f, src_pixel.y),
                           max(0.0f, src_pixel.z));

    if (bypass) {
      dst() = src_pixel;
      return;
    }

    float3 current_xyz = linear_srgb_to_xyz(in_rgb);
    float3 current_lab = xyz_to_oklab(current_xyz);
    float3 current_lch = oklab_to_oklch(current_lab);

    // --- Grade L and C ---
    float graded_L = (current_lch.x * l_gain) + l_offset;
    float safe_pivot = max(l_pivot, 0.0f);
    float safe_contrast = max(l_contrast, 0.0f);
    graded_L = ((graded_L - safe_pivot) * safe_contrast) + safe_pivot;
    float graded_C = (current_lch.y * c_gain) + c_offset;

    if (graded_L < 0.0f)
      graded_L = 0.0f;
    if (graded_C < 0.0f)
      graded_C = 0.0f;

    // --- Hue Curves: per-hue L/C multipliers ---
    if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
      float3 lut = sample_hue_lut(current_lch.z);
      float l_curve_mult = lut.z * 2.0f; // Blue channel
      float c_curve_mult = lut.y * 2.0f; // Green channel
      graded_L = max(graded_L * l_curve_mult, 0.0f);
      graded_C = max(graded_C * c_curve_mult, 0.0f);
    }

    // --- Grade H ---
    // Feature 1: Chroma-based weight.
    // Below hue_chroma_threshold, all hue shifts fade to zero -- achromatic
    // pixels (neutrals, near-blacks, near-whites) are left untouched.
    // smooth_ramp() is our own cubic Hermite (smoothstep is GLSL-only, not
    // Blink).
    float safe_threshold = max(hue_chroma_threshold, 0.0001f);
    float chroma_weight = smooth_ramp(0.0f, safe_threshold, current_lch.y);

    // Feature 2: Global hue shift weighted by chroma.
    float total_hue_shift = hue_shift_deg * chroma_weight;

    // Feature 2: Per-band hue shifts, each using a 60-degree half-width cosine
    // window. Band centre angles are perceptually placed on the OKLCH hue
    // wheel.
    float half = 60.0f;
    float orig_H = current_lch.z;

    total_hue_shift +=
        hue_shift_red * hue_band_weight(orig_H, 0.0f, half) * chroma_weight;
    total_hue_shift +=
        hue_shift_yellow * hue_band_weight(orig_H, 85.0f, half) * chroma_weight;
    total_hue_shift +=
        hue_shift_green * hue_band_weight(orig_H, 145.0f, half) * chroma_weight;
    total_hue_shift +=
        hue_shift_cyan * hue_band_weight(orig_H, 195.0f, half) * chroma_weight;
    total_hue_shift +=
        hue_shift_blue * hue_band_weight(orig_H, 265.0f, half) * chroma_weight;
    total_hue_shift += hue_shift_magenta *
                       hue_band_weight(orig_H, 325.0f, half) * chroma_weight;

    // Red band wraps around 360/0 -- add a second lobe at 360 to catch hues near
    // 360
    total_hue_shift +=
        hue_shift_red * hue_band_weight(orig_H, 360.0f, half) * chroma_weight;

    // Optional precise hue correction around a user-picked target hue.
    float safe_target_falloff = max(hue_target_falloff_deg, 0.1f);
    float target_weight =
        hue_band_weight(orig_H, wrap_hue_deg(hue_target_deg), safe_target_falloff) *
        chroma_weight;
    total_hue_shift += hue_target_shift * target_weight;

    // --- Hue Curves: per-hue hue offset ---
    if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
      float3 lut = sample_hue_lut(orig_H);
      float curve_hue_shift = (lut.x - 0.5f) * 360.0f; // Red channel
      total_hue_shift += curve_hue_shift * chroma_weight;
    }

    float graded_H = wrap_hue_deg(orig_H + total_hue_shift);

    // --- Debug modes ---
    if (debug_mode == 1) { // Lightness
      dst() = float4(graded_L, graded_L, graded_L, src_pixel.w);
      return;
    }
    if (debug_mode == 2) { // Chroma
      dst() = float4(graded_C, graded_C, graded_C, src_pixel.w);
      return;
    }
    if (debug_mode == 3) { // Hue
      float h_vis = graded_H / 360.0f;
      dst() = float4(h_vis, h_vis, h_vis, src_pixel.w);
      return;
    }
    if (debug_mode ==
        4) { // Chroma weight (visualise the achromatic falloff region)
      dst() = float4(chroma_weight, chroma_weight, chroma_weight, src_pixel.w);
      return;
    }
    if (debug_mode == 5) { // Hue Curves LUT values
      if (hue_curves_enable && hue_lut_connected && hue_lut_width > 1) {
        float3 lut = sample_hue_lut(orig_H);
        dst() = float4(lut.x, lut.y, lut.z, src_pixel.w);
      } else {
        dst() = float4(0.5f, 0.5f, 0.5f, src_pixel.w);
      }
      return;
    }

    // --- Reconstruct and blend ---
    float3 out_lab = oklch_to_oklab(float3(graded_L, graded_C, graded_H));
    float3 out_xyz = oklab_to_xyz(out_lab);
    float3 graded_rgb = xyz_to_linear_srgb(out_xyz);

    if (clamp_output) {
      graded_rgb.x = clamp01(graded_rgb.x);
      graded_rgb.y = clamp01(graded_rgb.y);
      graded_rgb.z = clamp01(graded_rgb.z);
    }

    float t = clamp(mix, 0.0f, 1.0f);
    float3 final_rgb = in_rgb + ((graded_rgb - in_rgb) * t);

    dst() = float4(final_rgb.x, final_rgb.y, final_rgb.z, src_pixel.w);
  }
};
