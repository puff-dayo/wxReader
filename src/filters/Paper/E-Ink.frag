#version 120

uniform sampler2D uTex;
uniform float uStrength;
varying vec2 vTex;

float rand(vec2 co){
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void main() {
    vec4 col = texture2D(uTex, vTex);
    float s = clamp(uStrength, 0.0, 1.0);

    float gray = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    float contrast = gray - 0.5;
    contrast = contrast * (1.0 + s * 0.5) + 0.5;
    contrast = clamp(contrast, 0.0, 1.0);

    float levels = 8.0;
    float quantized = floor(contrast * levels) / levels;

    vec3 eInkBg = vec3(0.92, 0.94, 0.90);
    vec3 inkColor = vec3(0.15, 0.15, 0.15);

    float noise = rand(vTex * 200.0) * 0.05 * s;

    vec3 finalGray = mix(inkColor, eInkBg, quantized + noise);

    col.rgb = mix(col.rgb, finalGray, s);

    gl_FragColor = vec4(col.rgb, 1.0);
}
