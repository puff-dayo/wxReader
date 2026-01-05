#version 120

uniform sampler2D uTex;
uniform float uSeed;
uniform float uStrength;

varying vec2 vTex;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * .1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

void main() {
    float s = clamp(uStrength, 0.0, 1.0);
    vec2 uv = vTex;
    vec4 bg = texture2D(uTex, uv);

    vec3 accColor = vec3(0.0);
    float accAlpha = 0.0;

    for (float i = 1.0; i <= 3.0; i++) {
        float scale = i * 15.0;
        vec2 grid = uv * scale;

        float wind = (uSeed - 50.0) * 0.02;
        grid.x += grid.y * wind * i;

        vec2 id = floor(grid);
        vec2 f = fract(grid) - 0.5;

        float n = hash12(id + uSeed * 50.0);

        vec2 p = f - (vec2(n, fract(n * 10.0)) - 0.5);

        float r = length(p);
        float size = 0.25 * n; // Random size

        float flake = smoothstep(size, size - 0.1, r);

        float density = step(0.5 + (0.4 * (1.0 - s)), n);

        accColor += vec3(1.0) * flake * density;
        accAlpha += flake * density;
    }

    float snowVisibility = clamp(accAlpha, 0.0, 0.6 * s);

    vec3 final = mix(bg.rgb, vec3(0.9, 0.95, 1.0), snowVisibility);

    float fog = s * 0.2;
    final = mix(final, vec3(0.8, 0.85, 0.9), fog);

    gl_FragColor = vec4(final, 1.0);
}
