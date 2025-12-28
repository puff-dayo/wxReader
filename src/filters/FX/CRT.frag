#version 120

uniform sampler2D uTex;
uniform float uTime;
varying vec2 vTex;

vec2 curve(vec2 uv) {
    uv = (uv - 0.5) * 2.0;
    uv.x *= 1.0 + pow((abs(uv.y) / 5.0), 2.0);
    uv.y *= 1.0 + pow((abs(uv.x) / 4.0), 2.0);
    return (uv / 2.0) + 0.5;
}

void main() {
    vec2 uv = curve(vTex);

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    float dist = distance(uv, vec2(0.5));
    vec2 offset = vec2(0.003 * dist, 0.0);

    float r = texture2D(uTex, uv + offset).r;
    float g = texture2D(uTex, uv).g;
    float b = texture2D(uTex, uv - offset).b;
    vec3 col = vec3(r, g, b);

    float scanline = sin((uv.y * 800.0) + (uTime * 5.0));
    col -= scanline * 0.05;

    float vig = uv.x * uv.y * (1.0 - uv.x) * (1.0 - uv.y);
    col *= pow(16.0 * vig, 0.2);

    col *= 1.0 + 0.01 * sin(110.0 * uTime);

    col *= 1.1;

    gl_FragColor = vec4(col, 1.0);
}
