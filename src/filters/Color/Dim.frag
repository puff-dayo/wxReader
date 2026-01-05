#version 120

uniform sampler2D uTex;

uniform float uStrength;
uniform float uDim;

varying vec2 vTex;

float luma(vec3 c) {
    return dot(c, vec3(0.299, 0.587, 0.114));
}

void main() {
    vec3 c = texture2D(uTex, vTex).rgb; // 0..1

    float strength = (uStrength <= 0.0) ? 0.85 : clamp(uStrength, 0.0, 1.0);
    strength = 1 - strength;
    float dim      = (uDim      <= 0.0) ? 0.70 : clamp(uDim,      0.0, 1.0);

    float y = luma(c);
    float high = smoothstep(0.65, 0.98, y);

    float darkFactor = 1.0 - (dim * 0.55 * strength) - (high * dim * 0.55 * strength);
    darkFactor = clamp(darkFactor, 0.15, 1.0);

    vec3 d = c * darkFactor;

    float gamma = mix(1.0, 1.18, 0.6 * strength);
    vec3 g = pow(d, vec3(gamma));

    float low = 1.0 - smoothstep(0.05, 0.25, y);
    vec3 keepText = mix(g, c, low * 0.35);

    vec3 outc = mix(c, keepText, strength);

    gl_FragColor = vec4(outc, 1.0);
}
