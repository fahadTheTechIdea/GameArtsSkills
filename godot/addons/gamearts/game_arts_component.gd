@tool
extends Node2D
## Game Arts v7.7 runtime component. Bundle + atlases are produced by the Python builders.
## Source PNGs stay opaque #FF00FF; the shader color-keys them at draw time.
## Attach this scene to a Godot 4 project under res://addons/gamearts/.

@export_file("*.json") var bundle_path: String = ""
@export var direction: String = "S":
    set(value):
        direction = value
        if is_node_ready():
            _apply_pose()
@export_range(0.0, 1.0, 0.001) var normalized_time: float = 0.0:
    set(value):
        normalized_time = clampf(value, 0.0, 1.0)
        if is_node_ready():
            _apply_pose()
@export var playing: bool = false
@export_range(0.01, 10.0, 0.01) var cycle_seconds: float = 1.0
@export var repeat_cycle: bool = true

const KEY_SHADER = preload("res://addons/gamearts/chroma_key.gdshader")
var _bundle: Dictionary = {}
var _components: Dictionary = {}
var _atlases: Dictionary = {}
var _textures: Dictionary = {}
var _nodes: Dictionary = {}
var _mount_nodes: Dictionary = {}
var _sprites: Dictionary = {}
var _invalid: bool = false

func _ready() -> void:
    if not bundle_path.is_empty():
        load_bundle(bundle_path)

func _process(delta: float) -> void:
    if playing and not _invalid and not _bundle.is_empty():
        var next_time: float = normalized_time + delta / maxf(cycle_seconds, 0.01)
        if repeat_cycle:
            normalized_time = fposmod(next_time, 1.0)
        else:
            normalized_time = minf(next_time, 1.0)
            if normalized_time >= 1.0:
                playing = false

func load_bundle(path: String) -> bool:
    playing = false
    _clear_parts()
    _invalid = true
    var raw := _read_json(path)
    if not (raw is Dictionary):
        push_error("Game Arts: missing or invalid bundle: " + path)
        return false
    var components = raw.get("components", [])
    var ordered = raw.get("component_order", [])
    var dirs = raw.get("directions", [])
    if not (components is Array and ordered is Array and dirs is Array and not dirs.is_empty()):
        push_error("Game Arts: malformed component bundle")
        return false
    var folder := path.get_base_dir()
    _bundle = raw
    _bundle["_folder"] = folder
    for part in components:
        if not (part is Dictionary and part.has("id")):
            push_error("Game Arts: invalid component entry")
            _clear_parts()
            return false
        _components[str(part["id"])] = part
    for id_value in ordered:
        var id := str(id_value)
        if not _components.has(id):
            push_error("Game Arts: invalid component order " + id)
            _clear_parts()
            return false
        var part: Dictionary = _components[id]
        var parent_id = part.get("parent")
        var parent_node: Node2D = self
        if parent_id != null:
            var pid := str(parent_id)
            if not _nodes.has(pid):
                push_error("Game Arts: parent missing or out of order: " + pid)
                _clear_parts()
                return false
            parent_node = _nodes[pid]
        var mount := Node2D.new()
        mount.name = "Mount_" + id
        parent_node.add_child(mount)
        _mount_nodes[id] = mount
        var node := Node2D.new()
        node.name = "Part_" + id
        mount.add_child(node)
        _nodes[id] = node
        var sprite := Sprite2D.new()
        sprite.name = "Sprite"
        sprite.centered = false
        sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
        sprite.material = ShaderMaterial.new()
        sprite.material.shader = KEY_SHADER
        node.add_child(sprite)
        _sprites[id] = sprite
        var views: Dictionary = {}
        var atlases = part.get("atlases", {})
        if not (atlases is Dictionary):
            _clear_parts()
            return false
        for dir_value in dirs:
            var d := str(dir_value)
            if not atlases.has(d):
                push_error("Game Arts: missing direction " + d + " for " + id)
                _clear_parts()
                return false
            var atlas_filename := str(atlases[d])
            if atlas_filename.get_file() != atlas_filename:
                push_error("Game Arts: unsafe atlas filename")
                _clear_parts()
                return false
            var atlas := _read_json(folder.path_join(atlas_filename))
            if not (atlas is Dictionary and atlas.has("frames")):
                push_error("Game Arts: missing atlas for " + id + "/" + d)
                _clear_parts()
                return false
            var image_filename := str(atlas.get("image", ""))
            if image_filename.get_file() != image_filename:
                _clear_parts()
                return false
            var texture := _load_texture(folder.path_join(image_filename))
            if texture == null:
                _clear_parts()
                return false
            views[d] = atlas
            _textures[id + "/" + d] = texture
        _atlases[id] = views
    if not dirs.has(direction):
        direction = str(dirs[0])
    _invalid = false
    _apply_pose()
    return true

func set_facing(new_direction: String) -> void:
    if not _bundle.is_empty() and _bundle.get("directions", []).has(new_direction):
        direction = new_direction  # Entire hierarchy updates in a single pose call.

func set_progress(time_0_to_1: float) -> void:
    normalized_time = clampf(time_0_to_1, 0.0, 1.0)

func _apply_pose() -> void:
    if _invalid or _bundle.is_empty():
        return
    # Pass 1: set every sprite's matching direction/frame before parent mounts.
    var frames: Dictionary = {}
    for id_value in _bundle.get("component_order", []):
        var id := str(id_value)
        var atlas: Dictionary = _atlases[id][direction]
        var arr: Array = atlas.get("frames", [])
        if arr.is_empty():
            return
        var idx: int = mini(int(normalized_time * arr.size()), arr.size() - 1)
        var f: Dictionary = arr[idx]
        frames[id] = f
        var sprite: Sprite2D = _sprites[id]
        sprite.texture = _textures[id + "/" + direction]
        sprite.region_enabled = true
        var rect: Array = f.get("rect", [])
        if rect.size() != 4:
            return
        sprite.region_rect = Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
        var pivot: Array = f.get("pivot", [])
        if pivot.size() != 2:
            return
        sprite.offset = Vector2(-float(pivot[0]), -float(pivot[1]))
    # Pass 2: transforms propagate through nested Node2D parentage.
    for id_value in _bundle.get("component_order", []):
        var id := str(id_value)
        var part: Dictionary = _components[id]
        var mount_node: Node2D = _mount_nodes[id]
        var parent_id = part.get("parent")
        var position := Vector2.ZERO
        var anchor_rotation := 0.0
        var anchor_scale := Vector2.ONE
        if parent_id != null:
            var pid := str(parent_id)
            var parent_frame: Dictionary = frames[pid]
            var anchors: Dictionary = parent_frame.get("anchors", {})
            var mount_name := str(part.get("mount", ""))
            if not anchors.has(mount_name):
                push_error("Game Arts: absent mount " + mount_name + " on " + pid)
                playing = false
                return
            var a: Array = anchors[mount_name]
            var p: Array = parent_frame["pivot"]
            position = Vector2(float(a[0] - p[0]), float(a[1] - p[1]))
            var action: String = str(part.get("parent_action") if part.get("parent_action") != null else _components[pid].get("action", "default"))
            var mount_track := _select_track(part.get("mount_tracks", {}), action, direction)
            var mt := _eval_track(mount_track, normalized_time)
            position += Vector2(mt.position[0], mt.position[1])
            anchor_rotation = mt.rotation_degrees
            anchor_scale = Vector2(mt.scale[0], mt.scale[1])
        mount_node.position = position
        mount_node.rotation_degrees = anchor_rotation
        mount_node.scale = anchor_scale
        var rest: Dictionary = _transform(part.get("rest", {}))
        var own_action := str(part.get("action", "default"))
        var own := _eval_track(_select_track(part.get("motion_tracks", {}), own_action, direction), normalized_time)
        var node: Node2D = _nodes[id]
        # Compose rest × child motion with an intermediate Node2D as needed.
        # For no shear, a rest transform combined with motion is evaluated in local space.
        var rp := Vector2(rest.position[0], rest.position[1])
        var rs := Vector2(rest.scale[0], rest.scale[1])
        var movement := Vector2(own.position[0], own.position[1])
        node.position = rp + movement.rotated(deg_to_rad(rest.rotation_degrees)) * rs
        node.rotation_degrees = rest.rotation_degrees + own.rotation_degrees
        node.scale = rs * Vector2(own.scale[0], own.scale[1])

func _select_track(tracks: Variant, action: String, d: String) -> Array:
    if not (tracks is Dictionary):
        return []
    var action_tracks: Variant = tracks.get(action, {})
    if not (action_tracks is Dictionary):
        return []
    var chosen: Variant = action_tracks.get(d, action_tracks.get("*", []))
    return chosen if chosen is Array else []

func _transform(raw: Variant) -> Dictionary:
    if not (raw is Dictionary):
        raw = {}
    return {"position": raw.get("position", [0, 0]),
            "rotation_degrees": float(raw.get("rotation_degrees", 0.0)),
            "scale": raw.get("scale", [1, 1])}

func _eval_track(keys: Array, t: float) -> Dictionary:
    if keys.is_empty():
        return _transform({})
    if keys.size() == 1 or t <= float(keys[0].get("time", 0)):
        return _transform(keys[0])
    if t >= float(keys[-1].get("time", 1)):
        return _transform(keys[-1])
    for i in range(1, keys.size()):
        var b: Dictionary = keys[i]
        if t <= float(b.get("time", 1)):
            var a: Dictionary = keys[i - 1]
            var ta: float = float(a.get("time", 0))
            var tb: float = float(b.get("time", 1))
            var u: float = clampf((t - ta) / maxf(tb - ta, 0.00001), 0, 1)
            var aa := _transform(a)
            var bb := _transform(b)
            var pa := Vector2(aa.position[0], aa.position[1])
            var pb := Vector2(bb.position[0], bb.position[1])
            var sa := Vector2(aa.scale[0], aa.scale[1])
            var sb := Vector2(bb.scale[0], bb.scale[1])
            return {"position": [lerpf(pa.x, pb.x, u), lerpf(pa.y, pb.y, u)],
                    "rotation_degrees": aa.rotation_degrees + wrapf(bb.rotation_degrees - aa.rotation_degrees + 180.0, 0.0, 360.0) * u - 180.0 * u,
                    "scale": [lerpf(sa.x, sb.x, u), lerpf(sa.y, sb.y, u)]}
    return _transform(keys[-1])

func _read_json(path: String) -> Variant:
    if not FileAccess.file_exists(path):
        return null
    var data := FileAccess.get_file_as_string(path)
    return JSON.parse_string(data)

func _load_texture(path: String) -> Texture2D:
    if not FileAccess.file_exists(path):
        push_error("Game Arts: missing source PNG " + path)
        return null
    var image := Image.new()
    if image.load(path) != OK:
        push_error("Game Arts: failed to load PNG " + path)
        return null
    if image.detect_alpha() != Image.ALPHA_NONE:
        # PNGs may have an alpha channel set to 255, so this is diagnostic only.
        pass
    return ImageTexture.create_from_image(image)

func _clear_parts() -> void:
    for n in _mount_nodes.values():
        if is_instance_valid(n) and n.get_parent() == self:
            n.queue_free()
    # Safe cleanup of child hierarchy; nodes are descendants of root mounts.
    for child in get_children():
        if child.name.begins_with("Mount_"):
            remove_child(child)
            child.queue_free()
    _bundle.clear()
    _components.clear()
    _atlases.clear()
    _textures.clear()
    _nodes.clear()
    _mount_nodes.clear()
    _sprites.clear()
