extends SceneTree
# Loads real framework output (written by run.py into res://data and described by res://expected.json) and prints what the engine made of it.
# It only observes. run.py compares every observation with what the framework itself computed.

const NEIGHBOUR := {
	"top": TileSet.CELL_NEIGHBOR_TOP_SIDE, "top_right": TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER, "right": TileSet.CELL_NEIGHBOR_RIGHT_SIDE,
	"bottom_right": TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER, "bottom": TileSet.CELL_NEIGHBOR_BOTTOM_SIDE,
	"bottom_left": TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER, "left": TileSet.CELL_NEIGHBOR_LEFT_SIDE, "top_left": TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER,
}

func read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	assert(file != null, "cannot open " + path)
	return JSON.parse_string(file.get_as_text())

func load_png(path: String) -> Image:
	return Image.load_from_file(ProjectSettings.globalize_path(path))

# --- the runtime sheet really has transparency where the key colour was
func probe_png(spec: Dictionary) -> Dictionary:
	var image := load_png(spec["png"])
	var transparent := 0
	var opaque := 0
	var partial := 0
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			var a := image.get_pixel(x, y).a
			if a == 0.0:
				transparent += 1
			elif a == 1.0:
				opaque += 1
			else:
				partial += 1
	return {"size": [image.get_width(), image.get_height()], "has_alpha_format": image.get_format() == Image.FORMAT_RGBA8, "transparent": transparent, "opaque": opaque, "partial": partial}

# --- SpriteFrames from the atlas: one animation per tag
func probe_tags(spec: Dictionary) -> Dictionary:
	var image := load_png(spec["png"])
	var texture := ImageTexture.create_from_image(image)
	var frames := SpriteFrames.new()
	frames.remove_animation("default")
	var out := {}
	for tag in spec["tags"]:
		var order: Array = range(int(tag["from"]), int(tag["to"]) + 1)
		if tag["direction"] == "reverse":
			order.reverse()
		frames.add_animation(tag["name"])
		frames.set_animation_loop(tag["name"], int(tag.get("repeat", 0)) == 0)
		frames.set_animation_speed(tag["name"], spec["fps"])
		var colours := []
		var durations := []
		for index in order:
			var frame: Dictionary = spec["frames"][index]
			var region := AtlasTexture.new()
			region.atlas = texture
			region.region = Rect2(frame["rect"][0], frame["rect"][1], frame["rect"][2], frame["rect"][3])
			frames.add_frame(tag["name"], region, float(frame["duration_ms"]) / spec["base_ms"])
			var centre := image.get_pixel(int(frame["rect"][0] + frame["rect"][2] / 2), int(frame["rect"][1] + frame["rect"][3] / 2))
			colours.append([int(round(centre.r * 255)), int(round(centre.g * 255)), int(round(centre.b * 255)), int(round(centre.a * 255))])
			durations.append(frames.get_frame_duration(tag["name"], frames.get_frame_count(tag["name"]) - 1))
		out[tag["name"]] = {"frames": frames.get_frame_count(tag["name"]), "loop": frames.get_animation_loop(tag["name"]), "speed": frames.get_animation_speed(tag["name"]),
			"frame_indexes": order, "durations": durations, "centre_colours": colours,
			"region_sizes": [frames.get_frame_texture(tag["name"], 0).get_width(), frames.get_frame_texture(tag["name"], 0).get_height()]}
	out["_names"] = Array(frames.get_animation_names())
	return out

# --- NinePatchRect and Button style boxes from the interface kit
func probe_ui(spec: Dictionary) -> Dictionary:
	var image := load_png(spec["png"])
	var texture := ImageTexture.create_from_image(image)
	var out := {"patches": {}, "states": {}}
	for panel in spec["panels"]:
		var patch := NinePatchRect.new()
		var region := AtlasTexture.new()
		region.atlas = texture
		region.region = Rect2(panel["rect"][0], panel["rect"][1], panel["rect"][2], panel["rect"][3])
		patch.texture = region
		patch.patch_margin_left = panel["nine_slice"][0]
		patch.patch_margin_top = panel["nine_slice"][1]
		patch.patch_margin_right = panel["nine_slice"][2]
		patch.patch_margin_bottom = panel["nine_slice"][3]
		patch.size = Vector2(panel["rect"][2] * 2, panel["rect"][3] * 2)
		out["patches"][panel["name"]] = {"margins": [patch.patch_margin_left, patch.patch_margin_top, patch.patch_margin_right, patch.patch_margin_bottom],
			"size": [patch.size.x, patch.size.y], "texture_size": [patch.texture.get_width(), patch.texture.get_height()]}
	var button := Button.new()
	for state in spec["states"]:
		var box := StyleBoxTexture.new()
		var region := AtlasTexture.new()
		region.atlas = texture
		region.region = Rect2(state["rect"][0], state["rect"][1], state["rect"][2], state["rect"][3])
		box.texture = region
		box.texture_margin_left = state["nine_slice"][0]
		box.texture_margin_top = state["nine_slice"][1]
		box.texture_margin_right = state["nine_slice"][2]
		box.texture_margin_bottom = state["nine_slice"][3]
		button.add_theme_stylebox_override(state["state"], box)
		var back := button.get_theme_stylebox(state["state"]) as StyleBoxTexture
		out["states"][state["state"]] = {"is_ours": back == box, "texture_size": [back.texture.get_width(), back.texture.get_height()],
			"margins": [back.texture_margin_left, back.texture_margin_top, back.texture_margin_right, back.texture_margin_bottom]}
	return out

# --- animation curves: the framework's keys with the engine's interpolation and transitions
func probe_curves(spec: Dictionary) -> Dictionary:
	var out := {}
	var transitions := {"linear": 1.0, "ease_in": 2.0, "ease_out": 0.5, "ease_in_out": -2.0}
	for curve in spec["curves"]:
		var animation := Animation.new()
		animation.length = 1.0
		var track := animation.add_track(Animation.TYPE_VALUE)
		animation.track_set_path(track, ".:x")
		var mode := Animation.INTERPOLATION_LINEAR
		if curve["interpolation"] == "nearest":
			mode = Animation.INTERPOLATION_NEAREST
		elif curve["interpolation"] == "cubic":
			mode = Animation.INTERPOLATION_CUBIC
		animation.track_set_interpolation_type(track, mode)
		for key in curve["keys"]:
			var transition: float = transitions[key.get("easing", "linear")]
			animation.track_insert_key(track, key["time"], key["value"], transition)
		var samples := []
		for t in spec["times"]:
			samples.append(snappedf(animation.value_track_interpolate(track, t), 0.0001))
		out[curve["name"]] = samples
	return out

# --- a tileset: terrain set from the neutral labels, then ask the engine to paint a block and report which tile it chose for each cell
func probe_tileset(spec: Dictionary) -> Dictionary:
	var meta: Dictionary = read_json(spec["tileset"])
	var atlas: Dictionary = read_json(spec["atlas"])
	var image := load_png(spec["png"])
	var tile_w: int = meta["tile_size"][0]
	var tile_h: int = meta["tile_size"][1]
	var columns: int = meta["columns"]
	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(tile_w, tile_h)
	tile_set.add_terrain_set()
	var mode := TileSet.TERRAIN_MODE_MATCH_CORNERS
	if meta["layout"] == "wang_edge_16":
		mode = TileSet.TERRAIN_MODE_MATCH_SIDES
	elif meta["layout"] == "blob_47":
		mode = TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES
	tile_set.set_terrain_set_mode(0, mode)
	var terrains: Array = meta["terrains"]
	for terrain in terrains:
		tile_set.add_terrain(0)
		tile_set.set_terrain_name(0, tile_set.get_terrains_count(0) - 1, terrain)
	var source := TileSetAtlasSource.new()
	source.texture = ImageTexture.create_from_image(image)
	source.texture_region_size = Vector2i(tile_w, tile_h)
	tile_set.add_source(source)
	var outside_is_empty: bool = spec["outside_is_empty"]
	var bit_count := 0
	for tile in meta["tiles"]:
		var coords := Vector2i(int(tile["id"]) % columns, int(tile["id"]) / columns)
		source.create_tile(coords)
		var data := source.get_tile_data(coords, 0)
		data.terrain_set = 0
		var inside := true
		for place in tile["neighbours"]:
			if tile["neighbours"][place] != terrains[0]:
				inside = false
		data.terrain = 0 if (inside or outside_is_empty or terrains.size() == 1) else (1 if _all_second(tile, terrains) else 0)
		for place in tile["neighbours"]:
			var index: int = terrains.find(tile["neighbours"][place])
			if index == 1 and outside_is_empty:
				index = -1
			data.set_terrain_peering_bit(NEIGHBOUR[place], index)
			bit_count += 1
	var back_ok := 0
	var back_total := 0
	for tile in meta["tiles"]:
		var coords := Vector2i(int(tile["id"]) % columns, int(tile["id"]) / columns)
		var data := source.get_tile_data(coords, 0)
		for place in tile["neighbours"]:
			var index: int = terrains.find(tile["neighbours"][place])
			if index == 1 and outside_is_empty:
				index = -1
			back_total += 1
			if data.get_terrain_peering_bit(NEIGHBOUR[place]) == index:
				back_ok += 1
	var layer := TileMapLayer.new()
	layer.tile_set = tile_set
	root.add_child(layer)
	var size: int = spec["map_size"]
	var block_from: int = spec["block_from"]
	var block_to: int = spec["block_to"]
	if not outside_is_empty:
		var all_cells := []
		for x in range(size):
			for y in range(size):
				all_cells.append(Vector2i(x, y))
		layer.set_cells_terrain_connect(all_cells, 0, 1)
	var block := []
	for x in range(block_from, block_to + 1):
		for y in range(block_from, block_to + 1):
			block.append(Vector2i(x, y))
	layer.set_cells_terrain_connect(block, 0, 0)
	var picked := []
	for y in range(size):
		var row := []
		for x in range(size):
			var cell := Vector2i(x, y)
			if layer.get_cell_source_id(cell) < 0:
				row.append(-1)
			else:
				var atlas_coords := layer.get_cell_atlas_coords(cell)
				row.append(atlas_coords.y * columns + atlas_coords.x)
		picked.append(row)
	return {"peering_bits_set": bit_count, "peering_bits_read_back_equal": back_ok, "peering_bits_read_back_total": back_total, "picked_tile_ids": picked,
		"atlas_frames": atlas["frames"].size(), "tile_count": meta["tiles"].size()}

func _all_second(tile: Dictionary, terrains: Array) -> bool:
	for place in tile["neighbours"]:
		if tile["neighbours"][place] != terrains[1]:
			return false
	return true

func _init():
	var spec: Dictionary = read_json("res://expected.json")
	var out := {"godot": Engine.get_version_info()["string"]}
	out["runtime_png"] = {}
	for name in spec["pngs"]:
		out["runtime_png"][name] = probe_png(spec["pngs"][name])
	out["tags"] = probe_tags(spec["tags"])
	out["ui"] = probe_ui(spec["ui"])
	out["curves"] = probe_curves(spec["curves"])
	out["tilesets"] = {}
	for name in spec["tilesets"]:
		out["tilesets"][name] = probe_tileset(spec["tilesets"][name])
	print("VERIFY_JSON ", JSON.stringify(out))
	quit(0)
