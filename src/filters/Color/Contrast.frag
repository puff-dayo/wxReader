#version 120

uniform sampler2D uTex;
uniform float uStrength;

varying vec2 vTex;

void main()
{
    vec4 src = texture2D(uTex, vTex);
    float strength = clamp(uStrength, 0.0, 1.0);
    float contrast = 1.0 + strength;
    vec3 result = (src.rgb - vec3(0.5)) * contrast + vec3(0.5);
    gl_FragColor = vec4(clamp(result, 0.0, 1.0), src.a);
}