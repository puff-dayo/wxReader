#version 120

uniform sampler2D uTex;
uniform float uStrength;
uniform vec2 uResolution;

varying vec2 vTex;

float luminance(vec3 color)
{
    return dot(color, vec3(0.299, 0.587, 0.114));
}

float bayer4(vec2 pixel)
{
    float x = mod(floor(pixel.x), 4.0);
    float y = mod(floor(pixel.y), 4.0);
    float value = 0.0;

    if (y < 1.0)
    {
        if      (x < 1.0) value = 0.0;
        else if (x < 2.0) value = 8.0;
        else if (x < 3.0) value = 2.0;
        else              value = 10.0;
    }
    else if (y < 2.0)
    {
        if      (x < 1.0) value = 12.0;
        else if (x < 2.0) value = 4.0;
        else if (x < 3.0) value = 14.0;
        else              value = 6.0;
    }
    else if (y < 3.0)
    {
        if      (x < 1.0) value = 3.0;
        else if (x < 2.0) value = 11.0;
        else if (x < 3.0) value = 1.0;
        else              value = 9.0;
    }
    else
    {
        if      (x < 1.0) value = 15.0;
        else if (x < 2.0) value = 7.0;
        else if (x < 3.0) value = 13.0;
        else              value = 5.0;
    }

    return (value + 0.5) / 16.0 - 0.5;
}

vec3 adjustColor(vec3 color, float strength)
{
    float luma = luminance(color);

    color = mix(
        vec3(luma),
        color,
        1.0 + 0.14 * strength
    );

    color = (color - 0.5)
        * (1.0 + 0.06 * strength)
        + 0.5;

    color *= mix(
        vec3(1.0),
        vec3(0.990, 0.998, 1.015),
        strength
    );

    return clamp(color, 0.0, 1.0);
}

vec3 quantize216(vec3 color, float dither)
{
    float intervals = 5.0;

    vec3 shifted = color + vec3(dither / intervals);
    shifted = clamp(shifted, 0.0, 1.0);

    return floor(shifted * intervals + 0.5) / intervals;
}

void main()
{
    float strength = clamp(uStrength, 0.0, 1.0);
    vec4 source = texture2D(uTex, vTex);
    vec3 prepared = adjustColor(source.rgb, strength);
    float dither = bayer4(gl_FragCoord.xy);

    vec3 paletteColor = quantize216(
        prepared,
        dither * strength
    );

    vec3 result = mix(
        source.rgb,
        paletteColor,
        strength
    );

    gl_FragColor = vec4(
        clamp(result, 0.0, 1.0),
        source.a
    );
}