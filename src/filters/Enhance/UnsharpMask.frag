#version 120

uniform sampler2D uTex;
uniform float uStrength;

varying vec2 vTex;

void main() {
    float step = 0.0015;
    float intensity = uStrength * 1.5;

    vec4 color = texture2D(uTex, vTex);

    vec4 u = texture2D(uTex, vTex + vec2(0.0, -step));
    vec4 d = texture2D(uTex, vTex + vec2(0.0, step));
    vec4 l = texture2D(uTex, vTex + vec2(-step, 0.0));
    vec4 r = texture2D(uTex, vTex + vec2(step, 0.0));

    vec4 blurred = (u + d + l + r) / 4.0;

    vec4 details = color - blurred;

    gl_FragColor = color + details * intensity;
}
