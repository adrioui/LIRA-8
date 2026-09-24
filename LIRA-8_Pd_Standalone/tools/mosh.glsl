// Single-tap datamosh.
uniform float motOffset;
out vec4 fragColor;
void main()
{
    vec4 mot = texture(sTD2DInputs[1], vUV.st);
    vec4 col = texture(sTD2DInputs[2], vUV.st + mot.rg * motOffset);
    fragColor = TDOutputSwizzle(col);
}
