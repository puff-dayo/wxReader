#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform float uDim;

varying vec2 vTex;

void main() {
    vec3 c = texture2D(uTex, vTex).rgb;

    float k = (uStrength <= 0.0) ? 1.0 : clamp(uStrength, 0.0, 1.0);

    float dim = (uDim <= 0.0) ? 0.25 : clamp(uDim, 0.0, 1.0);

    vec3 inv = 1.0 - c;

    inv *= (1.0 - 0.65 * dim);

    vec3 outc = mix(c, inv, k);

    gl_FragColor = vec4(outc, 1.0);
}
