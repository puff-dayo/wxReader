#version 120

uniform sampler2D uTex;
uniform float uStrength;
varying vec2 vTex;

float rand(vec2 co){
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void main() {
    vec4 color = texture2D(uTex, vTex);
    float s = clamp(uStrength, 0.0, 1.0);

    vec3 paperTint = vec3(0.98, 0.96, 0.92);
    vec3 currentTint = mix(vec3(1.0), paperTint, s);

    float noise = rand(vTex * 100.0);
    float grainStrength = 0.04 * s;
    vec3 grain = vec3(1.0 - grainStrength + noise * (grainStrength * 2.0));

    color.rgb *= currentTint * grain;

    float gamma = 1.0 + 0.1 * s;
    color.rgb = pow(color.rgb, vec3(gamma));

    gl_FragColor = color;
}
