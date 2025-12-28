#version 120

uniform sampler2D uTex;
varying vec2 vTex;

float rand(vec2 co){
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void main() {
    vec4 color = texture2D(uTex, vTex);

    vec3 paperTint = vec3(0.98, 0.96, 0.92);

    float noise = rand(vTex * 100.0);
    float grainStrength = 0.04;
    vec3 grain = vec3(1.0 - grainStrength + noise * (grainStrength * 2.0));

    color.rgb *= paperTint * grain;

    color.rgb = pow(color.rgb, vec3(1.1));

    gl_FragColor = color;
}
