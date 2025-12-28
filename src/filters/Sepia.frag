#version 120

uniform sampler2D uTex;
uniform float uStrength;
varying vec2 vTex;

void main() {
    vec3 c = texture2D(uTex, vTex).rgb;

    vec3 s;
    s.r = (393.0*c.r + 769.0*c.g + 189.0*c.b) / 1000.0;
    s.g = (349.0*c.r + 686.0*c.g + 168.0*c.b) / 1000.0;
    s.b = (272.0*c.r + 534.0*c.g + 131.0*c.b) / 1000.0;

    s = clamp(s, 0.0, 1.0);

    float k = (uStrength <= 0.0) ? 1.0 : uStrength;
    vec3 outc = mix(c, s, clamp(k, 0.0, 1.0));

    gl_FragColor = vec4(outc, 1.0);
}
