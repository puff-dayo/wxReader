#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform vec2 uResolution;
varying vec2 vTex;

float rand(vec2 co) {
    return fract(sin(dot(co.xy, vec2(12.9898, 78.233))) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);

    float a = rand(i);
    float b = rand(i + vec2(1.0, 0.0));
    float c = rand(i + vec2(0.0, 1.0));
    float d = rand(i + vec2(1.0, 1.0));

    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

void main() {
    vec4 color = texture2D(uTex, vTex);
    float s = clamp(uStrength, 0.0, 1.0);

    vec2 uv = vTex;

    vec3 paperTint = vec3(0.965, 0.955, 0.925);
    vec3 tint = mix(vec3(1.0), paperTint, s);

    float cloud = noise(uv * 8.0);
    cloud += noise(uv * 18.0) * 0.5;
    cloud /= 1.5;

    float fiberX = noise(vec2(uv.x * 260.0, uv.y * 28.0));
    float fiberY = noise(vec2(uv.x * 36.0, uv.y * 220.0));

    float fibers = fiberX * 0.65 + fiberY * 0.35;

    float fineGrain = rand(uv * uResolution.xy);

    float paperTexture =
        1.0
        + (cloud - 0.5) * 0.045 * s
        + (fibers - 0.5) * 0.035 * s
        + (fineGrain - 0.5) * 0.018 * s;

    vec2 centered = uv - 0.5;
    float vignette = 1.0 - dot(centered, centered) * 0.16 * s;

    vec3 result = color.rgb;

    result *= tint;
    result *= paperTexture;
    result *= vignette;

    float gray = dot(result, vec3(0.299, 0.587, 0.114));
    result = mix(result, vec3(gray), 0.04 * s);

    gl_FragColor = vec4(clamp(result, 0.0, 1.0), color.a);
}