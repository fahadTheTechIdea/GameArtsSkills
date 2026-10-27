extends SceneTree

func v2(v: Vector2) -> Array:
	return [snappedf(v.x, 0.01), snappedf(v.y, 0.01)]

func grid_probe(shape: int, axis: int, layout: int, size: Vector2i) -> Dictionary:
	var ts := TileSet.new()
	ts.tile_shape = shape
	ts.tile_layout = layout
	ts.tile_offset_axis = axis
	ts.tile_size = size
	var layer := TileMapLayer.new()
	layer.tile_set = ts
	root.add_child(layer)
	var result := {
		"origin": v2(layer.map_to_local(Vector2i(0, 0))),
		"x+1": v2(layer.map_to_local(Vector2i(1, 0))),
		"y+1": v2(layer.map_to_local(Vector2i(0, 1))),
		"y+2": v2(layer.map_to_local(Vector2i(0, 2))),
	}
	layer.queue_free()
	return result

func r4(x: float) -> float:
	return snappedf(x, 0.0001)

func probe_animation_and_ui(out: Dictionary) -> void:
	# interpolation: enum values and what each does between two keys
	out["animation_interpolation_enum"] = {"NEAREST": Animation.INTERPOLATION_NEAREST, "LINEAR": Animation.INTERPOLATION_LINEAR,
		"CUBIC": Animation.INTERPOLATION_CUBIC, "LINEAR_ANGLE": Animation.INTERPOLATION_LINEAR_ANGLE, "CUBIC_ANGLE": Animation.INTERPOLATION_CUBIC_ANGLE}
	var curves := {}
	for mode_name in ["NEAREST", "LINEAR", "CUBIC"]:
		var anim := Animation.new()
		anim.length = 1.0
		var track := anim.add_track(Animation.TYPE_VALUE)
		anim.track_set_path(track, ".:x")
		anim.track_set_interpolation_type(track, out["animation_interpolation_enum"][mode_name])
		anim.track_insert_key(track, 0.0, 0.0)
		anim.track_insert_key(track, 0.5, 10.0)
		anim.track_insert_key(track, 1.0, 0.0)
		var samples := []
		for t in [0.1, 0.25, 0.4, 0.5, 0.75]:
			samples.append(r4(anim.value_track_interpolate(track, t)))
		curves[mode_name] = samples
	out["animation_value_samples_at_0.1_0.25_0.4_0.5_0.75_for_keys_0_10_0_at_0_0.5_1"] = curves

	# easing: the key transition value; sample u = 0.25, 0.5, 0.75 of a 0 -> 100 segment for a few transitions
	var easing := {}
	for transition in [0.5, 1.0, 2.0, -2.0, -0.5, 0.0]:
		var anim2 := Animation.new()
		anim2.length = 1.0
		var track2 := anim2.add_track(Animation.TYPE_VALUE)
		anim2.track_set_path(track2, ".:x")
		anim2.track_set_interpolation_type(track2, Animation.INTERPOLATION_LINEAR)
		anim2.track_insert_key(track2, 0.0, 0.0, transition)
		anim2.track_insert_key(track2, 1.0, 100.0)
		var vals := []
		for u in [0.25, 0.5, 0.75]:
			vals.append(r4(anim2.value_track_interpolate(track2, u)))
		easing[str(transition)] = vals
	out["animation_key_transition_samples_at_u_0.25_0.5_0.75_of_0_to_100"] = easing

	# blend modes
	out["canvas_item_blend_modes"] = {"MIX": CanvasItemMaterial.BLEND_MODE_MIX, "ADD": CanvasItemMaterial.BLEND_MODE_ADD, "SUB": CanvasItemMaterial.BLEND_MODE_SUB,
		"MUL": CanvasItemMaterial.BLEND_MODE_MUL, "PREMULT_ALPHA": CanvasItemMaterial.BLEND_MODE_PREMULT_ALPHA}
	var material := CanvasItemMaterial.new()
	material.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	out["canvas_item_material_blend_mode_set"] = material.blend_mode
	var blend_names := []
	for property in material.get_property_list():
		if property["name"] == "blend_mode":
			blend_names.append(property["hint_string"])
	out["canvas_item_material_blend_mode_hint"] = blend_names

	# nine slice
	var patch := NinePatchRect.new()
	patch.patch_margin_left = 6
	patch.patch_margin_top = 5
	patch.patch_margin_right = 4
	patch.patch_margin_bottom = 3
	out["nine_patch_margins_left_top_right_bottom"] = [patch.patch_margin_left, patch.patch_margin_top, patch.patch_margin_right, patch.patch_margin_bottom]
	var patch_props := []
	for property in patch.get_property_list():
		if str(property["name"]).begins_with("patch_margin") or property["name"] in ["axis_stretch_horizontal", "axis_stretch_vertical", "draw_center", "region_rect"]:
			patch_props.append(property["name"])
	out["nine_patch_properties"] = patch_props

	# ui states: the style boxes a Button theme has
	var theme := ThemeDB.get_default_theme()
	var boxes := Array(theme.get_stylebox_list("Button"))
	boxes.sort()
	out["button_stylebox_names"] = boxes

	# tile terrain modes and the neighbours a tile exposes per mode
	var terrain_modes := {"MATCH_CORNERS_AND_SIDES": TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES, "MATCH_CORNERS": TileSet.TERRAIN_MODE_MATCH_CORNERS,
		"MATCH_SIDES": TileSet.TERRAIN_MODE_MATCH_SIDES}
	out["tileset_terrain_modes"] = terrain_modes
	var neighbours := {"RIGHT_SIDE": TileSet.CELL_NEIGHBOR_RIGHT_SIDE, "BOTTOM_RIGHT_CORNER": TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER, "BOTTOM_SIDE": TileSet.CELL_NEIGHBOR_BOTTOM_SIDE,
		"BOTTOM_LEFT_CORNER": TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER, "LEFT_SIDE": TileSet.CELL_NEIGHBOR_LEFT_SIDE, "TOP_LEFT_CORNER": TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER,
		"TOP_SIDE": TileSet.CELL_NEIGHBOR_TOP_SIDE, "TOP_RIGHT_CORNER": TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER}
	out["tileset_cell_neighbours"] = neighbours
	var valid_bits := {}
	for mode_name in terrain_modes:
		var ts := TileSet.new()
		ts.tile_size = Vector2i(8, 8)
		ts.add_terrain_set()
		ts.set_terrain_set_mode(0, terrain_modes[mode_name])
		ts.add_terrain(0)
		var source := TileSetAtlasSource.new()
		var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
		source.texture = ImageTexture.create_from_image(image)
		source.texture_region_size = Vector2i(8, 8)
		source.create_tile(Vector2i(0, 0))
		ts.add_source(source)
		var data := source.get_tile_data(Vector2i(0, 0), 0)
		data.terrain_set = 0
		var valid := []
		for neighbour_name in neighbours:
			if data.is_valid_terrain_peering_bit(neighbours[neighbour_name]):
				valid.append(neighbour_name)
		valid_bits[mode_name] = valid
	out["tile_data_valid_peering_bits_by_terrain_mode"] = valid_bits

	# sprite frames: a named animation, loop flag, speed
	var frames := SpriteFrames.new()
	frames.add_animation("walk")
	frames.set_animation_loop("walk", false)
	frames.set_animation_speed("walk", 12.0)
	out["spriteframes_walk"] = {"loop": frames.get_animation_loop("walk"), "speed": frames.get_animation_speed("walk")}
	var anim_sprite := AnimatedSprite2D.new()
	var methods := []
	for method in anim_sprite.get_method_list():
		if str(method["name"]) in ["play", "play_backwards", "pause", "stop", "set_frame_and_progress"]:
			methods.append(method["name"])
	methods.sort()
	out["animated_sprite_2d_playback_methods"] = methods
	var has_pingpong := false
	for property in anim_sprite.get_property_list():
		if "pingpong" in str(property["name"]).to_lower() or "ping_pong" in str(property["name"]).to_lower():
			has_pingpong = true
	out["animated_sprite_2d_has_pingpong_property"] = has_pingpong
	var loop_modes := {"NONE": Animation.LOOP_NONE, "LINEAR": Animation.LOOP_LINEAR, "PINGPONG": Animation.LOOP_PINGPONG}
	out["animation_loop_modes"] = loop_modes

func _init():
	var out := {}
	out["godot"] = Engine.get_version_info()["string"]

	# atlas_frame_rect: an exclusive top-left [x, y, w, h] rectangle is a Rect2 region
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	image.fill(Color(1, 0, 1))
	var texture := ImageTexture.create_from_image(image)
	var region := AtlasTexture.new()
	region.atlas = texture
	region.region = Rect2(8, 4, 20, 10)
	out["atlas_region_size"] = [region.get_width(), region.get_height()]

	# frame_duration: relative duration per frame and one speed per animation
	var frames := SpriteFrames.new()
	frames.add_animation("walk")
	frames.set_animation_speed("walk", 10.0)
	frames.add_frame("walk", region, 1.0)
	frames.add_frame("walk", region, 2.0)
	out["spriteframes"] = {"speed": frames.get_animation_speed("walk"), "count": frames.get_frame_count("walk"),
		"durations": [frames.get_frame_duration("walk", 0), frames.get_frame_duration("walk", 1)]}

	# frame_pivot: one node offset places the pivot (the atlas gives every frame the same cell-local pivot)
	var sprite := Sprite2D.new()
	sprite.centered = false
	sprite.offset = Vector2(-16, -31)
	out["sprite_pivot"] = {"centered": sprite.centered, "offset": v2(sprite.offset)}

	# grids: hexagon pointy / flat, isometric diamond
	out["hex_offset_horizontal"] = grid_probe(TileSet.TILE_SHAPE_HEXAGON, TileSet.TILE_OFFSET_AXIS_HORIZONTAL, TileSet.TILE_LAYOUT_STACKED, Vector2i(64, 56))
	out["hex_offset_vertical"] = grid_probe(TileSet.TILE_SHAPE_HEXAGON, TileSet.TILE_OFFSET_AXIS_VERTICAL, TileSet.TILE_LAYOUT_STACKED, Vector2i(64, 56))
	out["iso_diamond_down"] = grid_probe(TileSet.TILE_SHAPE_ISOMETRIC, TileSet.TILE_OFFSET_AXIS_HORIZONTAL, TileSet.TILE_LAYOUT_DIAMOND_DOWN, Vector2i(64, 32))

	# parallax_layer
	var parallax := Parallax2D.new()
	parallax.scroll_scale = Vector2(0.4, 0)
	parallax.repeat_size = Vector2(1024, 0)
	parallax.autoscroll = Vector2(4, 0)
	out["parallax2d"] = {"scroll_scale": v2(parallax.scroll_scale), "repeat_size": v2(parallax.repeat_size), "autoscroll": v2(parallax.autoscroll)}

	# project settings the profile names, with the options the engine itself lists for them
	var names := ["rendering/textures/canvas_textures/default_texture_filter", "display/window/size/viewport_width",
		"display/window/size/viewport_height", "display/window/stretch/mode", "display/window/stretch/scale_mode",
		"rendering/2d/snap/snap_2d_transforms_to_pixel", "rendering/2d/snap/snap_2d_vertices_to_pixel"]
	var settings := {}
	for property in ProjectSettings.get_property_list():
		if names.has(property["name"]):
			settings[property["name"]] = {"hint_string": property["hint_string"], "default": str(ProjectSettings.property_get_revert(property["name"]))}
	out["settings"] = settings

	probe_animation_and_ui(out)

	print("VERIFY_JSON ", JSON.stringify(out))
	quit(0)
