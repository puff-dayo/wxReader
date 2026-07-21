#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform vec2 uResolution;
uniform float uSeed;

varying vec2 vTex;

float rand(vec2 p) {
    return fract(
        sin(dot(p, vec2(127.1, 311.7)) + uSeed * 13.17)
        * 43758.5453123
    );
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

float luminance(vec3 color) {
    return dot(color, vec3(0.299, 0.587, 0.114));
}

void main() {
    vec4 src = texture2D(uTex, vTex);
    float s = clamp(uStrength, 0.0, 1.0);

    vec2 uv = vTex;
    vec2 px = uv * max(uResolution, vec2(1.0));

    vec3 paperColor = vec3(1.000, 0.985, 0.900);

    float sourceLightness = luminance(src.rgb);
    float paperMask = smoothstep(0.56, 0.95, sourceLightness);

    vec3 result = src.rgb;

    float brightnessLift =
        (1.0 - sourceLightness)
        * 0.050
        * paperMask
        * s;

    result += vec3(brightnessLift);

    float tintAmount = 0.78 * paperMask * s;
    result = mix(result, paperColor, tintAmount);

    float finePulp =
        noise(uv * 5.0) * 0.50 +
        noise(uv * 15.0) * 0.32 +
        noise(uv * 42.0) * 0.18;

    float cloudy =
        noise(uv * vec2(3.5, 2.4)) * 0.62 +
        noise(uv * vec2(9.0, 7.0)) * 0.38;

    float paperVariation =
        (finePulp - 0.5) * 0.020 +
        (cloudy - 0.5) * 0.010;

    result += vec3(paperVariation) * paperMask * s;
    
    float fiberSeed =
        rand(floor(px * 0.55) + vec2(31.0, 97.0));

    float fiber = step(0.9965, fiberSeed);
    float fiberShape =
        smoothstep(
            0.30,
            0.90,
            noise(vec2(px.x * 0.35, px.y * 0.10))
        );

    fiber *= fiberShape;

    result -=
        fiber
        * paperMask
        * vec3(0.014, 0.010, 0.004)
        * s;

    gl_FragColor = vec4(clamp(result, 0.0, 1.0), src.a);
}
