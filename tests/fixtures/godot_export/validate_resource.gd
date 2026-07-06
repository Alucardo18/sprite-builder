extends SceneTree


func _init() -> void:
	var resource := load("res://generated/walk_right.sprite_frames.tres")
	if not resource is SpriteFrames:
		push_error("Export did not load as SpriteFrames")
		quit(2)
		return
	if not resource.has_animation(&"walk_right"):
		push_error("walk_right animation missing")
		quit(3)
		return
	if resource.get_frame_count(&"walk_right") != 2:
		push_error("Unexpected frame count")
		quit(4)
		return
	print("SPRITE_BUILDER_GODOT_EXPORT_OK")
	quit(0)
