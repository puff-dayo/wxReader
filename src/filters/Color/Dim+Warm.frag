#version 120

uniform sampler2D uTex;
uniform float uStrength;

varying vec2 vTex;

float luma(vec3 c) {
    return dot(c, vec3(0.299, 0.587, 0.114));
}

void main() {
    vec3 c = texture2D(uTex, vTex).rgb;

    float s = clamp(1 - uStrength, 0.0, 1.0);

    float MAX_DIM = 0.75;
    float MAX_WARM = 0.80;

    float dimLevel = MAX_DIM * s;
    float warmLevel = MAX_WARM * s;

    float y = luma(c);

    float high = smoothstep(0.60, 0.95, y);

    float darkFactor = 1.0 - (dimLevel * 0.5) - (high * dimLevel * 0.5);
    darkFactor = clamp(darkFactor, 0.10, 1.0);

    vec3 dimmed = c * darkFactor;

    vec3 warmed = vec3(
        dimmed.r * (1.0 + 0.12 * warmLevel),
        dimmed.g * (1.0 + 0.05 * warmLevel),
        dimmed.b * (1.0 - 0.20 * warmLevel)
    );
    warmed = clamp(warmed, 0.0, 1.0);

    float gamma = 1.0 + (0.15 * s);
    vec3 g = pow(warmed, vec3(gamma));

    float low = 1.0 - smoothstep(0.05, 0.30, y);
    vec3 keepText = mix(g, c, low * 0.30);

    gl_FragColor = vec4(mix(c, keepText, s), 1.0);
}
