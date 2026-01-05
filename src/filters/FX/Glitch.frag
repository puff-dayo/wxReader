#version 120

uniform sampler2D uTex;
uniform float uSeed;
uniform float uStrength;

varying vec2 vTex;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float hash11(float p) {
    return fract(sin(p) * 43758.5453123);
}

vec3 neonPalette(float t) {
    if (t < 0.25) return vec3(1.0, 0.0, 1.0); // magenta
    if (t < 0.50) return vec3(0.0, 1.0, 1.0); // cyan
    if (t < 0.75) return vec3(1.0, 1.0, 0.0); // yellow
    return vec3(0.0, 0.0, 0.0);               // black
}

void main() {
    float s = clamp(uStrength, 0.0, 1.0);
    vec2 uv = vTex;

    float bands = 180.0;
    float bandId = floor(uv.y * bands);

    float bandRnd = hash11(bandId + uSeed * 100.0);

    float glitchThreshold = 1.0 - (0.3 * s);
    float isBand = step(glitchThreshold, bandRnd);

    float bandShift = (bandRnd - 0.5) * 0.15 * s;

    uv.x += isBand * bandShift;

    float chRnd = hash12(vec2(bandId, uSeed * 17.0));
    float maxShift = 0.02 * s;
    float rShift = (chRnd - 0.5) * maxShift;
    float bShift = -(chRnd - 0.5) * maxShift * 0.8;

    vec3 col;
    col.r = texture2D(uTex, vec2(uv.x + rShift, uv.y)).r;
    col.g = texture2D(uTex, uv).g;
    col.b = texture2D(uTex, vec2(uv.x + bShift, uv.y)).b;

    vec2 grid = vec2(30.0, 20.0);
    vec2 cell = floor(uv * grid);
    float cellRnd = hash12(cell + uSeed * 99.0);

    float blockThreshold = 1.0 - (0.10 * s);
    float blockOn = step(blockThreshold, cellRnd);

    vec2 f = fract(uv * grid);
    float inset = 0.1 + 0.3 * hash12(cell + 9.1);
    float inside = step(inset, f.x) * step(inset, f.y) *
                   step(inset, 1.0 - f.x) * step(inset, 1.0 - f.y);

    float blockMask = blockOn * inside;

    vec3 glitchCol = neonPalette(hash12(cell + 3.7 + uSeed));

    float scan = 0.05 * s * sin(uv.y * 800.0);
    col += scan;

    col = mix(col, glitchCol, blockMask);

    gl_FragColor = vec4(col, 1.0);
}
