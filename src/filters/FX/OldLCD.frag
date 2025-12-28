#version 120

uniform sampler2D uTex;
varying vec2 vTex;

void main() {
    vec4 color = texture2D(uTex, vTex);

    // Adjust 900.0/600.0 to change "pixel density"
    float gridX = abs(sin(vTex.x * 900.0));
    float gridY = abs(sin(vTex.y * 600.0));
    float grid = clamp((gridX + gridY) * 0.5, 0.0, 1.0);

    color.rgb *= 1.0 - (grid * 0.15);

    float gray = dot(color.rgb, vec3(0.3, 0.59, 0.11));
    color.rgb = mix(color.rgb, vec3(gray), 0.2);

    vec3 blackLift = vec3(0.12, 0.15, 0.14);
    color.rgb = mix(blackLift, vec3(1.0), color.rgb);

    float levels = 32.0;
    color.rgb = floor(color.rgb * levels) / levels;

    gl_FragColor = vec4(color.rgb, 1.0);
}
