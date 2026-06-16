extends CharacterBody2D
## 玩家农夫：键盘走动（唯一移动方式，方案 D11）+ 四向动画 + 脚步声 + 头顶气泡。
## 跨地点移动的协议触发（zone 检测）由 main.gd 负责，本脚本只管表现层。
##
## W7 画面升级：节点原点=脚底（Y-sort）/ 脚下软阴影 / 名牌 pill /
## 气泡 Q 弹+打字机+淡出 / 相机 limit_smoothed / 走路扬尘。

var _sprite: AnimatedSprite2D
var _footstep: AudioStreamPlayer
var _bubble_wrap: Node2D
var _bubble: Label
var _bubble_timer := 0.0
var _facing := "down"
var _dust: CPUParticles2D


func _ready() -> void:
	add_to_group("player")
	var tex: Texture2D = load(Config.NA_CHARS[0])   # 草帽农夫（玩家）
	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = SpriteLib.build(tex)
	_sprite.scale = Vector2.ONE * Config.CHAR_SCALE
	_sprite.offset = Vector2(0, -8)   # W7 Y-sort：节点原点=脚底
	_sprite.play("idle_down")
	add_child(_sprite)

	var shadow := SpriteLib.make_shadow(26.0)
	shadow.position = Vector2(0, -2)
	add_child(shadow)

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(12, 8) * Config.CHAR_SCALE
	shape.shape = rect
	shape.position = Vector2(0, -3 * Config.CHAR_SCALE)  # 碰撞贴脚部（原点已是脚底）
	add_child(shape)

	var cam := Camera2D.new()
	cam.zoom = Vector2(1.0, 1.0)
	# W7：limit 四向内缩 32px——树墙封边始终可见，不露世界外纯色
	cam.limit_left = int(Config.WORLD_RECT.position.x) + 32
	cam.limit_top = int(Config.WORLD_RECT.position.y) + 32
	cam.limit_right = int(Config.WORLD_RECT.end.x) - 32
	cam.limit_bottom = int(Config.WORLD_RECT.end.y) - 32
	cam.position_smoothing_enabled = true
	cam.position_smoothing_speed = 7.0
	cam.limit_smoothed = true
	add_child(cam)

	_footstep = AudioStreamPlayer.new()
	_footstep.stream = load("res://assets/audio/footstep.wav")
	_footstep.volume_db = -10.0
	add_child(_footstep)

	_build_bubble()

	# 名牌 pill（与 NPC 同款，主题色绿）
	var name_panel := PanelContainer.new()
	name_panel.add_theme_stylebox_override("panel", SpriteLib.make_panel_style())
	name_panel.position = Vector2(-18, -70)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	var dot := ColorRect.new()
	dot.color = Config.NPC_COLORS.get(0, Color.WHITE)
	dot.custom_minimum_size = Vector2(8, 8)
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(dot)
	var name_label := Label.new()
	name_label.text = "我"
	name_label.add_theme_font_size_override("font_size", 12)
	row.add_child(name_label)
	name_panel.add_child(row)
	add_child(name_panel)

	# 走路扬尘
	_dust = SpriteLib.make_particles(6, 0.4)
	_dust.emitting = false
	_dust.gravity = Vector2.ZERO
	_dust.initial_velocity_min = 4.0
	_dust.initial_velocity_max = 10.0
	_dust.scale_amount_min = 2.0
	_dust.scale_amount_max = 3.0
	_dust.color = Color(0.8, 0.72, 0.55, 0.45)
	_dust.show_behind_parent = true
	add_child(_dust)


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
		Config.WORLD_RECT.position + Vector2(16, 48),
		Config.WORLD_RECT.end - Vector2(16, 4),
	)
	_animate(dir)
	_tick_bubble(_delta)


func _animate(dir: Vector2) -> void:
	if dir == Vector2.ZERO:
		_sprite.play("idle_%s" % _facing)
		_dust.emitting = false
		if _footstep.playing:
			_footstep.stop()
	else:
		_facing = SpriteLib.dir_name(dir, _facing)
		_sprite.play("walk_%s" % _facing)
		_dust.emitting = true
		if not _footstep.playing:
			_footstep.play()


const BUBBLE_BASE_Y := -76.0
const BUBBLE_MAX_CHARS := 48       # 气泡显示软上限（W10 配合短句对话）


## 头顶气泡（自己当面说的话本地回显，方案 D18）
func show_bubble(text: String) -> void:
	var shown := text
	if shown.length() > BUBBLE_MAX_CHARS:
		shown = shown.substr(0, BUBBLE_MAX_CHARS) + "…"
	_bubble.text = shown
	_bubble_timer = Config.BUBBLE_SECONDS
	SpriteLib.pop_bubble(_bubble_wrap, _bubble)


func _tick_bubble(delta: float) -> void:
	if _bubble_wrap.visible and _bubble_timer > 0.0:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			SpriteLib.fade_bubble(_bubble_wrap)


# ---- W9 气泡去重堆叠（供 main 的 BubbleDeclutter 调用）----

func bubble_visible() -> bool:
	return _bubble_wrap != null and _bubble_wrap.visible


func set_bubble_lift(px: float) -> void:
	if _bubble_wrap != null:
		_bubble_wrap.position.y = BUBBLE_BASE_Y - px


func bubble_global_rect() -> Rect2:
	return _bubble.get_global_rect()


func _build_bubble() -> void:
	_bubble_wrap = Node2D.new()
	_bubble_wrap.visible = false
	_bubble_wrap.position = Vector2(0, BUBBLE_BASE_Y)
	_bubble_wrap.z_index = 100   # W9：气泡恒在最上层
	_bubble = Label.new()
	_bubble.position = Vector2(-90, -52)
	_bubble.custom_minimum_size = Vector2(180, 0)
	_bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_bubble.add_theme_font_size_override("font_size", 12)
	_bubble.add_theme_color_override("font_color", Color(0.1, 0.1, 0.1))
	var theme_color: Color = Config.NPC_COLORS.get(0, Color.WHITE)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 1, 1, 0.94)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.border_width_left = 2
	style.border_width_right = 2
	style.border_width_top = 2
	style.border_width_bottom = 2
	style.border_color = theme_color
	style.content_margin_left = 8.0
	style.content_margin_right = 8.0
	style.content_margin_top = 4.0
	style.content_margin_bottom = 4.0
	_bubble.add_theme_stylebox_override("normal", style)
	_bubble_wrap.add_child(_bubble)
	var tail := Polygon2D.new()
	tail.polygon = PackedVector2Array([Vector2(-6, -2), Vector2(6, -2), Vector2(0, 8)])
	tail.color = theme_color
	_bubble_wrap.add_child(tail)
	add_child(_bubble_wrap)
