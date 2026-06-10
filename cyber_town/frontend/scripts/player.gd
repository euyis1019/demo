extends CharacterBody2D
## 玩家农夫：键盘走动（唯一移动方式，方案 D11）+ 四向动画 + 脚步声 + 头顶气泡。
## 跨地点移动的协议触发（zone 检测）由 main.gd 负责，本脚本只管表现层。

var _sprite: AnimatedSprite2D
var _footstep: AudioStreamPlayer
var _bubble: Label
var _bubble_timer := 0.0
var _facing := "down"


func _ready() -> void:
	add_to_group("player")
	var tex: Texture2D = load("res://assets/gfx/character.png")
	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = SpriteLib.build(tex)
	_sprite.scale = Vector2.ONE * Config.SPRITE_SCALE
	_sprite.play("idle_down")
	add_child(_sprite)

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(14, 10) * Config.SPRITE_SCALE
	shape.shape = rect
	shape.position = Vector2(0, 10 * Config.SPRITE_SCALE)  # 碰撞贴脚部
	add_child(shape)

	var cam := Camera2D.new()
	cam.zoom = Vector2(1.0, 1.0)
	cam.limit_left = int(Config.WORLD_RECT.position.x)
	cam.limit_top = int(Config.WORLD_RECT.position.y)
	cam.limit_right = int(Config.WORLD_RECT.end.x)
	cam.limit_bottom = int(Config.WORLD_RECT.end.y)
	cam.position_smoothing_enabled = true
	add_child(cam)

	_footstep = AudioStreamPlayer.new()
	_footstep.stream = load("res://assets/audio/footstep.wav")
	_footstep.volume_db = -10.0
	add_child(_footstep)

	_bubble = _make_bubble()
	add_child(_bubble)

	var name_label := Label.new()
	name_label.text = "我"
	name_label.position = Vector2(-12, -40 * Config.SPRITE_SCALE / 2 - 14)
	name_label.add_theme_font_size_override("font_size", 12)
	name_label.add_theme_color_override("font_color", Color(1, 1, 0.85))
	add_child(name_label)


func _physics_process(_delta: float) -> void:
	var dir := Vector2(
		(1.0 if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT) else 0.0)
		- (1.0 if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT) else 0.0),
		(1.0 if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN) else 0.0)
		- (1.0 if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP) else 0.0),
	)
	if get_tree().get_first_node_in_group("ui_blocking"):
		dir = Vector2.ZERO  # 菜单/输入框打开时禁走（M3 用）
	velocity = dir.normalized() * Config.PLAYER_SPEED if dir != Vector2.ZERO else Vector2.ZERO
	move_and_slide()
	# 困在世界边界内
	position = position.clamp(
		Config.WORLD_RECT.position + Vector2(16, 32),
		Config.WORLD_RECT.end - Vector2(16, 16),
	)
	_animate(dir)
	_tick_bubble(_delta)


func _animate(dir: Vector2) -> void:
	if dir == Vector2.ZERO:
		_sprite.play("idle_%s" % _facing)
		if _footstep.playing:
			_footstep.stop()
	else:
		_facing = SpriteLib.dir_name(dir, _facing)
		_sprite.play("walk_%s" % _facing)
		if not _footstep.playing:
			_footstep.play()


## 头顶气泡（自己当面说的话本地回显，方案 D18）
func show_bubble(text: String) -> void:
	_bubble.text = text
	_bubble.visible = true
	_bubble_timer = Config.BUBBLE_SECONDS


func _tick_bubble(delta: float) -> void:
	if _bubble.visible:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			_bubble.visible = false


func _make_bubble() -> Label:
	var l := Label.new()
	l.visible = false
	l.position = Vector2(-90, -40 * Config.SPRITE_SCALE - 10)
	l.custom_minimum_size = Vector2(180, 0)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 13)
	l.add_theme_color_override("font_color", Color(0.1, 0.1, 0.1))
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 1, 1, 0.92)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 8.0
	style.content_margin_right = 8.0
	style.content_margin_top = 4.0
	style.content_margin_bottom = 4.0
	l.add_theme_stylebox_override("normal", style)
	return l
