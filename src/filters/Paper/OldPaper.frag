#version 120

uniform sampler2D uTex;
uniform float uTime;
uniform float uStrength;
varying vec2 vTex;

float rand(vec2 n) {
    return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
}

float noise(vec2 p){
    vec2 ip = floor(p);
    vec2 u = fract(p);
    u = u*u*(3.0-2.0*u);
    float res = mix(
        mix(rand(ip), rand(ip+vec2(1.0,0.0)), u.x),
        mix(rand(ip+vec2(0.0,1.0)), rand(ip+vec2(1.0,1.0)), u.x), u.y);
    return res*res;
}

void main() {
    vec4 texColor = texture2D(uTex, vTex);
    float s = clamp(uStrength, 0.0, 1.0);

    vec3 oldPaperColor = vec3(0.92, 0.86, 0.76);
    vec3 currentTint = mix(vec3(1.0), oldPaperColor, s);

    float spot = noise(vTex * 5.0);
    vec3 stains = vec3(1.0) - (0.1 * spot * s);

    vec2 uv = vTex * (1.0 - vTex.yx);
    float vigBase = uv.x * uv.y * 15.0;
    float vig = pow(vigBase, 0.07);
    float vigApplied = mix(1.0, vig, s);

    vec3 finalColor = texColor.rgb;

    finalColor *= currentTint;
    finalColor *= stains;
    finalColor *= vigApplied;

    gl_FragColor = vec4(finalColor, 1.0);
}
