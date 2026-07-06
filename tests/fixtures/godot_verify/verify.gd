extends SceneTree


func _init() -> void:
	var frames := load("res://generated.sprite_frames.tres") as SpriteFrames
	if frames == null:
		push_error("SPRITE_BUILDER_GODOT_LOAD_FAILED")
		quit(2)
		return
	if not frames.has_animation(&"walk_right"):
		push_error("SPRITE_BUILDER_GODOT_ANIMATION_MISSING")
		quit(3)
		return
	if frames.get_frame_count(&"walk_right") != 4:
		push_error("SPRITE_BUILDER_GODOT_FRAME_COUNT_INVALID")
		quit(4)
		return
	print("SPRITE_BUILDER_GODOT_EXPORT_OK")
	quit(0)
