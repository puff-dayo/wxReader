#version 120
uniform sampler2D uTex;
varying vec2 vTex;

void main() {
    vec3 c = texture2D(uTex, vTex).rgb;
    float g = dot(c, vec3(0.299, 0.587, 0.114));
    gl_FragColor = vec4(g, g, g, 1.0);
}
