kernel OKLCHGrade : ImageComputationKernel<ePixelWise> {
  Image<eRead, eAccessPoint, eEdgeClamped> src;
  Image<eWrite> dst;

param:
  float l_gain;
  float l_offset;
  float c_gain;
  float c_offset;
  float hue_shift_deg;
  float mix;
  bool clamp_output;
  bool bypass;

local:
  float pi;
  float deg_per_rad;
  float epsilon;

  void define() {
    defineParam(l_gain, "L Gain", 1.0f);
    defineParam(l_offset, "L Offset", 0.0f);
    defineParam(c_gain, "C Gain", 1.0f);
    defineParam(c_offset, "C Offset", 0.0f);
    defineParam(hue_shift_deg, "Hue Shift (deg)", 0.0f);
    defineParam(mix, "Mix", 1.0f);
    defineParam(clamp_output, "Clamp Output", false);
    defineParam(bypass, "Bypass", false);
  }

  void init() {
    pi = 3.14159265358979323846f;
    deg_per_rad = 57.2957795130823208768f;
    epsilon = 0.000004f;
  }

  float signed_cbrt(float x) {
    if (x == 0.0f) {
      return 0.0f;
    }

    if (x > 0.0f) {
      return pow(x, 1.0f / 3.0f);
    }

    return -pow(-x, 1.0f / 3.0f);
  }

  float clamp01(float x) { return clamp(x, 0.0f, 1.0f); }

  float wrap_hue_deg(float h) {
    // Use fmod (not floor) — floor is not in the BlinkScript math surface.
    float wrapped = fmod(h, 360.0f);
    if (wrapped < 0.0f) {
      wrapped += 360.0f;
    }
    return wrapped;
  }

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
    float h = atan2(lab.z, lab.y) * deg_per_rad;

    if (h < 0.0f) {
      h += 360.0f;
    }

    if (c <= epsilon) {
      h = 0.0f;
    }

    return float3(lab.x, c, h);
  }

  float3 oklch_to_oklab(float3 lch) {
    float rad = lch.z * (pi / 180.0f);
    float a = lch.y * cos(rad);
    float b = lch.y * sin(rad);
    return float3(lch.x, a, b);
  }

  void process() {
    float4 rgba = src();
    float3 in_rgb =
        float3(max(0.0f, rgba.x), max(0.0f, rgba.y), max(0.0f, rgba.z));

    if (bypass) {
      dst() = rgba;
      return;
    }

    float3 xyz = linear_srgb_to_xyz(in_rgb);
    float3 lab = xyz_to_oklab(xyz);
    float3 lch = oklab_to_oklch(lab);

    float L = (lch.x * l_gain) + l_offset;
    float C = (lch.y * c_gain) + c_offset;
    float H = wrap_hue_deg(lch.z + hue_shift_deg);

    if (L < 0.0f) {
      L = 0.0f;
    }

    if (C < 0.0f) {
      C = 0.0f;
    }

    float3 graded_lab = oklch_to_oklab(float3(L, C, H));
    float3 graded_xyz = oklab_to_xyz(graded_lab);
    float3 graded_rgb = xyz_to_linear_srgb(graded_xyz);

    if (clamp_output) {
      graded_rgb.x = clamp01(graded_rgb.x);
      graded_rgb.y = clamp01(graded_rgb.y);
      graded_rgb.z = clamp01(graded_rgb.z);
    }

    float t = clamp(mix, 0.0f, 1.0f);
    float3 out_rgb = in_rgb + ((graded_rgb - in_rgb) * t);

    dst() = float4(out_rgb.x, out_rgb.y, out_rgb.z, rgba.w);
  }
};
