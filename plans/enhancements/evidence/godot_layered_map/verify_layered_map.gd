extends SceneTree
# Loads a layered map written by the framework (res://data, described by res://expected.json) and prints what the engine did with its layers.
# It only observes. run.py compares every observation with what the framework computed. Nothing is rendered, so draw order is NOT observed.

func read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	assert(file != null, "cannot open " + path)
	return JSON.parse_string(file.get_as_text())

func load_texture(path: String) -> ImageTexture:
	return ImageTexture.create_from_image(Image.load_from_file(ProjectSettings.globalize_path(path)))

# One TileMapLayer per overlay, drawn on the dual grid: a display tile sits where four cells meet, so the layer is offset by half a cell.
func probe_overlay(spec: Dictionary, cell: Array, parent: Node2D) -> Dictionary:
	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(int(spec["tile"][0]), int(spec["tile"][1]))
	var source := TileSetAtlasSource.new()
	source.texture = load_texture(spec["png"])
	source.texture_region_size = tile_set.tile_size
	var columns := int(spec["columns"])
	for i in range(int(spec["frames"])):
		source.create_tile(Vector2i(i % columns, i / columns))
	tile_set.add_source(source)
	var layer := TileMapLayer.new()
	layer.name = spec["layer"]
	layer.tile_set = tile_set
	layer.position = Vector2(-float(cell[0]) / 2.0, -float(cell[1]) / 2.0)
	parent.add_child(layer)
	for entry in spec["cells"]:
		var id := int(entry[2])
		layer.set_cell(Vector2i(int(entry[0]), int(entry[1])), 0, Vector2i(id % columns, id / columns))
	var back := []
	var world := []
	for entry in spec["cells"]:
		var at := Vector2i(int(entry[0]), int(entry[1]))
		var coords := layer.get_cell_atlas_coords(at)
		back.append(coords.y * columns + coords.x)
		var junction := layer.position + layer.map_to_local(at)
		world.append([junction.x, junction.y])
	return {"tile_count": source.get_tiles_count(), "used_cells": layer.get_used_cells().size(), "ids_back": back, "junction_world": world}

# Small objects as atlas tiles on a y-sorted layer. A tile sits on a cell, so a free pixel position can only be approximated by the cell it falls in.
func probe_tile_objects(spec: Dictionary, cell: Array, parent: Node2D) -> Dictionary:
	var rocks: Dictionary = spec["rocks"]
	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(int(cell[0]), int(cell[1]))
	tile_set.add_physics_layer()
	var source := TileSetAtlasSource.new()
	source.texture = load_texture(rocks["png"])
	source.texture_region_size = Vector2i(int(rocks["frame_size"][0]), int(rocks["frame_size"][1]))
	source.separation = Vector2i(int(rocks["separation"]), int(rocks["separation"]))
	var columns := int(rocks["columns"])
	tile_set.add_source(source)  # the tile set must own the source before its tiles can hold collision data (found: setting it before drops the polygon silently)
	var y_origins := []
	var polygons := []
	for i in range(int(rocks["tile_frames"])):
		var at := Vector2i(i % columns, i / columns)
		source.create_tile(at)
		var data: TileData = source.get_tile_data(at, 0)
		data.y_sort_origin = int(rocks["pivot_y_from_centre"])
		var half_w := float(spec["footprint"][0]) / 2.0
		var h := float(spec["footprint"][1])
		var base := float(rocks["pivot_y_from_centre"])
		data.add_collision_polygon(0)
		data.set_collision_polygon_points(0, 0, PackedVector2Array([Vector2(-half_w, base - h), Vector2(half_w, base - h), Vector2(half_w, base), Vector2(-half_w, base)]))
		y_origins.append(data.y_sort_origin)
		polygons.append(data.get_collision_polygons_count(0))
	var layer := TileMapLayer.new()
	layer.name = "objects_as_tiles"
	layer.tile_set = tile_set
	layer.y_sort_enabled = true
	parent.add_child(layer)
	var snapped := []
	for obj in spec["objects"]:
		var at := Vector2i(int(obj["x"]) / int(cell[0]), int(obj["y"]) / int(cell[1]))
		layer.set_cell(at, 0, Vector2i(int(obj["frame"]) % columns, int(obj["frame"]) / columns))
		snapped.append([at.x, at.y])
	var points: PackedVector2Array = source.get_tile_data(Vector2i(0, 0), 0).get_collision_polygon_points(0, 0)
	var observed_points := []
	for p in points:
		observed_points.append([p.x, p.y])
	return {"used_cells": layer.get_used_cells().size(), "y_sort_enabled": layer.y_sort_enabled, "y_sort_origins": y_origins, "polygons_per_tile": polygons,
			"polygon_points": observed_points, "snapped_cells": snapped, "collision_enabled_default": layer.collision_enabled}

# Free pixel positions need sprites; they are placed exactly.
func probe_sprite_objects(spec: Dictionary, parent: Node2D) -> Dictionary:
	var rocks: Dictionary = spec["rocks"]
	var holder := Node2D.new()
	holder.name = "objects_as_sprites"
	holder.y_sort_enabled = true
	parent.add_child(holder)
	var texture := load_texture(rocks["png"])
	var positions := []
	for obj in spec["objects"]:
		var sprite := Sprite2D.new()
		var rect: Array = rocks["frames"][int(obj["frame"])]
		sprite.texture = texture
		sprite.region_enabled = true
		sprite.region_rect = Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
		sprite.centered = false
		sprite.offset = Vector2(-float(rocks["pivot"][0]), -float(rocks["pivot"][1]))
		sprite.position = Vector2(float(obj["x"]), float(obj["y"]))
		holder.add_child(sprite)
		positions.append([sprite.position.x, sprite.position.y])
	return {"count": holder.get_child_count(), "positions": positions, "y_sort_enabled": holder.y_sort_enabled}

func _init() -> void:
	var spec: Dictionary = read_json("res://expected.json")
	var root := Node2D.new()
	root.name = "Map"
	get_root().add_child(root)
	var order := []
	var overlays := {}
	for overlay in spec["overlays"]:
		overlays[overlay["layer"]] = probe_overlay(overlay, spec["cell"], root)
		order.append(overlay["layer"])
	var tile_objects := probe_tile_objects(spec, spec["cell"], root)
	var sprite_objects := probe_sprite_objects(spec, root)
	var children := []
	for child in root.get_children():
		children.append(String(child.name))
	print("VERIFY_JSON " + JSON.stringify({"godot": Engine.get_version_info()["string"], "overlays": overlays, "tile_objects": tile_objects,
			"sprite_objects": sprite_objects, "children_in_order": children}))
	quit()
