#version 120

uniform sampler2D uTex;
uniform float uStrength;

varying vec2 vTex;

void main()
{
    vec4 src = texture2D(uTex, vTex);
    float strength = clamp(uStrength, 0.0, 1.0);
    vec3 result = mix(
        src.rgb,
        vec3(1.0),
        0.25 * strength
    );
    gl_FragColor = vec4(clamp(result, 0.0, 1.0), src.a);
}