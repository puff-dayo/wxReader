#version 120

uniform sampler2D uTex;
uniform float uStrength;

varying vec2 vTex;

void main() {
    float step = 0.001;

    vec4 center = texture2D(uTex, vTex);

    vec4 up     = texture2D(uTex, vTex + vec2(0.0, -step));
    vec4 left   = texture2D(uTex, vTex + vec2(-step, 0.0));
    vec4 right  = texture2D(uTex, vTex + vec2(step, 0.0));
    vec4 down   = texture2D(uTex, vTex + vec2(0.0, step));

    //  0 -1  0
    // -1  4 -1
    //  0 -1  0
    vec4 edge = center * 4.0 - (up + left + right + down);

    vec4 finalColor = center + uStrength * edge;

    gl_FragColor = finalColor;
}
