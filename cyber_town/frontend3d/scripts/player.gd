extends Node3D
## 玩家农夫（3D）：键盘 WASD 在 XZ 平面走动，y 贴地（Config.ground_y），billboard 立绘。
## 跨地点协议触发（zone 检测）由 main 负责；本脚本只管移动与表现。菜单打开时禁走。

var _spr: AnimatedSprite3D
var _facing := "down"
var _footstep: AudioStreamPlayer
var _bubble: Label3D
var _bubble_timer := 0.0


func _ready() -> void:
	add_to_group("player")
	_spr = SpriteLib3D.make_char_sprite(load(Config.CHARS[0]), Config.CHAR_PX)
	add_child(_spr)
	add_child(SpriteLib3D.make_blob(load(Config.T_BLOB), 0.5))

	var name_l := SpriteLib3D.make_label(48, Config.NPC_COLORS[0])
	name_l.text = "我"
	name_l.position = Vector3(0, 2.0, 0)
	add_child(name_l)

	_bubble = SpriteLib3D.make_label(44, Color(1, 1, 0.85))
	_bubble.position = Vector3(0, 2.5, 0)
	_bubble.width = 600
	_bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble.visible = false
	add_child(_bubble)

	_footstep = AudioStreamPlayer.new()
	var fs := load("res://assets/audio/footstep.wav")
	if fs != null:
		_footstep.stream = fs
		_footstep.volume_db = -12.0
	add_child(_footstep)


func _process(delta: float) -> void:
	var blocked := get_tree().get_first_node_in_group("ui_blocking") != null
	var ix := 0.0
	var iz := 0.0
	if not blocked:
		ix = (1.0 if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT) else 0.0) \
			- (1.0 if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT) else 0.0)
		iz = (1.0 if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN) else 0.0) \
			- (1.0 if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP) else 0.0)
	var dir := Vector3(ix, 0, iz)
	if dir.length() > 0.01:
		dir = dir.normalized()
		var np := position + dir * Config.PLAYER_SPEED * delta
		np.x = clampf(np.x, Config.WORLD.position.x + 1, Config.WORLD.end.x - 1)
		np.z = clampf(np.z, Config.WORLD.position.y + 1, Config.WORLD.end.y - 1)
		np.y = Config.ground_y(Vector2(np.x, np.z))
		position = np
		_facing = SpriteLib3D.dir_name(Vector2(ix, iz), _facing)
		_spr.play("walk_%s" % _facing)
		if not _footstep.playing and _footstep.stream != null:
			_footstep.play()
	else:
		_spr.play("idle_%s" % _facing)
		if _footstep.playing:
			_footstep.stop()
	if _bubble.visible:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			_bubble.visible = false


## 头顶气泡（自己当面说的话本地回显）
func show_bubble(text: String) -> void:
	var shown := text
	if shown.length() > 40:
		shown = shown.substr(0, 40) + "…"
	_bubble.text = shown
	_bubble.visible = true
	_bubble_timer = Config.BUBBLE_SECONDS
