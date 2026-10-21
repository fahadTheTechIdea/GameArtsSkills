shader_type canvas_item;
render_mode unshaded;

// Game Arts PNGs stay opaque #FF00FF.
// Remove the key only when rendering; never edit the source image.
void fragment() {
    vec4 pixel_color = texture(TEXTURE, UV);
    if (distance(pixel_color.rgb, vec3(1.0, 0.0, 1.0)) < 0.001) {
        discard;
    }
    COLOR = pixel_color;
}
