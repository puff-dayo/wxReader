#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform float uTime;

varying vec2 vTex;

void main() {
    // Offset for neighbor sampling.
    // 0.001 corresponds to roughly 1 pixel for a 1000px wide image.
    // Adjust this if the blur radius is too large or too small.
    float offset = 0.001;
    float mixFactor = uStrength * 0.4;

    vec4 center = texture2D(uTex, vTex);

    vec4 up     = texture2D(uTex, vTex + vec2(0.0, -offset));
    vec4 down   = texture2D(uTex, vTex + vec2(0.0, offset));
    vec4 left   = texture2D(uTex, vTex + vec2(-offset, 0.0));
    vec4 right  = texture2D(uTex, vTex + vec2(offset, 0.0));


    vec4 blurred = (center + up + down + left + right) / 5.0;
    gl_FragColor = mix(center, blurred, mixFactor);
}
