extends SceneTree
## Launch: godot --headless --path tests/_godot_generated --script res://test_runtime.gd

var _failures: Array[String] = []

func _assert(value: bool, message: String) -> void:
    if not value:
        _failures.append(message)
        printerr("FAIL: ", message)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var packed := load("res://test_component.tscn") as PackedScene
    _assert(packed != null, "generated test scene parses")
    if packed == null:
        _finish()
        return
    var rig = packed.instantiate()
    _assert(rig != null, "test scene instantiates")
    if rig == null:
        _finish()
        return
    root.add_child(rig)
    await process_frame
    _assert(rig.get("_invalid") == false, "bundle and atlases load")
    _assert(rig.get("_components").size() == 3, "all components created")
    _assert(rig.get("_sprites").size() == 3, "all sprite sheets loaded")
    var parts: Dictionary = rig.get("_nodes")
    _assert(parts.has("base") and parts.has("joint") and parts.has("tip"), "nested parts exist")
    if parts.size() == 3:
        _assert(parts["tip"].get_parent().get_parent() == parts["joint"], "tip parent hierarchy")
    rig.call("set_progress", 0.0)
    var joint_mount: Node2D = rig.get("_mount_nodes")["joint"]
    var start_position: Vector2 = joint_mount.position
    var start_rotation: float = joint_mount.rotation_degrees
    rig.call("set_progress", 1.0)
    _assert(joint_mount.position != start_position, "animated attachment translates")
    _assert(absf(joint_mount.rotation_degrees - start_rotation) > 1.0, "animated attachment rotates")
    var time_before: float = float(rig.get("normalized_time"))
    rig.call("set_facing", "E")
    _assert(str(rig.get("direction")) == "E", "facing switches")
    _assert(is_equal_approx(float(rig.get("normalized_time")), time_before), "direction preserves animation progress")
    var sprites: Dictionary = rig.get("_sprites")
    var atlases: Dictionary = rig.get("_atlases")
    for id in sprites:
        var sprite: Sprite2D = sprites[id]
        _assert(sprite.texture != null, "texture exists: " + id)
        _assert(sprite.material is ShaderMaterial, "chroma key shader applied: " + id)
        _assert(sprite.region_rect.size.x > 0, "sprite region valid: " + id)
        _assert(atlases[id].has("E"), "new direction atlas present: " + id)
    rig.set("playing", true)
    rig.set("cycle_seconds", 1.0)
    rig.set("repeat_cycle", true)
    var playback_before: float = float(rig.get("normalized_time"))
    await process_frame
    await process_frame
    _assert(float(rig.get("normalized_time")) != playback_before, "animation progresses while playing")
    # Child may animate on a separate normalized clock while its parent moves.
    rig.call("set_component_progress", "tip", 0.25)
    _assert(rig.get("_component_phases").has("tip"), "independent child phase stored")
    rig.call("clear_component_progress", "tip")
    _assert(not rig.get("_component_phases").has("tip"), "child phase restored to shared clock")
    rig.queue_free()
    _finish()

func _finish() -> void:
    if _failures.size() > 0:
        printerr("Game Arts Godot smoke tests failed: ", _failures.size())
        quit(1)
    else:
        print("PASS: Game Arts Godot runtime hierarchy, playback, direction, anchors, shader")
        quit(0)
