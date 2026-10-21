shader_type canvas_item;
render_mode unshaded;

// Game Arts source textures remain fully opaque #FF00FF.
// Remove only exact chroma-pink at RUNTIME; never modify delivered PNG files.
void fragment() {
    vec4 pixel_color = texture(TEXTURE, UV);
    if (distance(pixel_color.rgb, vec3(1.0, 0.0, 1.0)) < 0.001) {
        discard;
    }
    COLOR = pixel_color * COLOR;
}
