#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform float uDim;
uniform float uWarmth;
varying vec2 vTex;

void main() {
    vec3 c = texture2D(uTex, vTex).rgb;

    float k = (uStrength <= 0.0) ? 1.0 : clamp(uStrength, 0.0, 1.0);
    float dim = (uDim <= 0.0) ? 0.25 : clamp(uDim, 0.0, 1.0);
    float w = (uWarmth <= 0.0) ? 0.15 : clamp(uWarmth, 0.0, 1.0);

    vec3 inv = 1.0 - c;

    inv *= (1.0 - 0.65 * dim);

    inv = vec3(
        inv.r * (1.0 + 0.18 * w),
        inv.g * (1.0 + 0.10 * w),
        inv.b * (1.0 - 0.22 * w)
    );
    inv = clamp(inv, 0.0, 1.0);

    vec3 outc = mix(c, inv, k);

    gl_FragColor = vec4(outc, 1.0);
}
