#version 120

uniform sampler2D uTex;
varying vec2 vTex;

void main() {
    vec4 texColor = texture2D(uTex, vTex);

    float brightness = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));

    vec3 blueBg = vec3(0.05, 0.15, 0.45);
    vec3 whiteInk = vec3(0.9, 0.95, 1.0);

    vec2 gridPos = fract(vTex * 50.0);
    float gridLine = step(0.95, gridPos.x) + step(0.95, gridPos.y);
    gridLine = clamp(gridLine, 0.0, 1.0);

    vec3 bgWithGrid = mix(blueBg, blueBg * 1.3, gridLine * 0.3);

    vec3 finalColor = mix(whiteInk, bgWithGrid, brightness);

    gl_FragColor = vec4(finalColor, 1.0);
}
