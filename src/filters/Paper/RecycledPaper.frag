#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform vec2 uResolution;
uniform float uSeed;

varying vec2 vTex;

float rand(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7)) + uSeed * 13.17) * 43758.5453123);
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
    vec4 src = texture2D(uTex, vTex);
    float us = uStrength + 0.2;
    float s = clamp(us, 0.0, 1.0);
    vec2 uv = vTex;
    vec2 px = uv * uResolution.xy;

    vec3 basePaper = vec3(0.690, 0.710, 0.635);

    float pulp =
        noise(uv * 3.5) * 0.45 +
        noise(uv * 9.0) * 0.35 +
        noise(uv * 22.0) * 0.20;

    float cloudy =
        noise(uv * vec2(6.0, 4.0)) * 0.6 +
        noise(uv * vec2(14.0, 11.0)) * 0.4;

    float shortFiberSeed = rand(floor(px / 2.5));
    float shortFiber = step(0.965, shortFiberSeed);

    float fiberShape = smoothstep(0.15, 0.95, noise(vec2(px.x * 0.75, px.y * 0.18)));
    shortFiber *= fiberShape;

    float r1 = rand(floor(px) + vec2(19.0, 73.0));
    float r2 = rand(floor(px * 0.65) + vec2(91.0, 11.0));
    float r3 = rand(floor(px * 0.42) + vec2(37.0, 157.0));

    float blackFleck = step(0.9965, r1);
    float grayFleck  = step(0.9915, r2);
    float brownFleck = step(0.9940, r3);

    float pressLine = sin(uv.y * uResolution.y * 0.42);
    pressLine = pressLine * 0.5 + 0.5;
    pressLine = (pressLine - 0.5) * 0.012;

    vec3 result = src.rgb;

    result *= mix(vec3(1.0), basePaper, 0.72 * s);

    result *= 1.0 + (pulp - 0.5) * 0.105 * s;
    result *= 1.0 + (cloudy - 0.5) * 0.060 * s;

    result *= 1.0 + pressLine * s;

    result -= shortFiber * vec3(0.025, 0.030, 0.020) * s;

    result -= blackFleck * vec3(0.120, 0.110, 0.095) * s;
    result -= grayFleck  * vec3(0.055, 0.060, 0.052) * s;
    result -= brownFleck * vec3(0.075, 0.055, 0.032) * s;

    float lightPulp = step(0.995, rand(floor(px * 0.8) + vec2(211.0, 47.0)));
    result += lightPulp * vec3(0.035, 0.038, 0.025) * s;

    float gray = dot(result, vec3(0.299, 0.587, 0.114));
    result = mix(result, vec3(gray), 0.10 * s);

    gl_FragColor = vec4(clamp(result, 0.0, 1.0), src.a);
}