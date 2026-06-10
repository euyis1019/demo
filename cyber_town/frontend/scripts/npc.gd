extends Node2D
## 村民 NPC 表现层：跨地点平滑步行（WALKING）+ 锚点游走（WANDER）+
## 头顶气泡/状态条。引擎态只有离散 place；坐标/动画全为前端推断（方案 §7.3）。
## 用 position 插值，不走物理（避免与玩家推挤）。

enum State { IDLE, WANDER, WALKING }

signal clicked(npc_id: int)      # M6：点击村民 → 档案页

var npc_id: int = -1
var display_name := ""
var anchor_index := 0            # 由 main 按地点到场顺序分配

var _state: State = State.IDLE
var _place := ""                 # 引擎确认的当前地点
var _anchor := Vector2.ZERO      # 当前地点锚点（游走圆心）
var _target := Vector2.ZERO      # 当前移动目标
var _wander_timer := 0.0
var _facing := "down"

var _sprite: AnimatedSprite2D
var _name_label: Label
var _state_label: Label
var _bubble: Label
var _bubble_timer := 0.0


func _ready() -> void:
	# 按 agent_id 取专属村民外观（老钱=白须老者/阿香=紫发女/大山=橙衣壮汉）
	var tex_path: String = Config.NA_CHARS.get(npc_id, Config.NA_CHARS[3])
	var tex: Texture2D = load(tex_path)
	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = SpriteLib.build(tex)
	_sprite.scale = Vector2.ONE * Config.CHAR_SCALE
	_sprite.play("idle_down")
	add_child(_sprite)

	_name_label = Label.new()
	_name_label.text = display_name
	_name_label.position = Vector2(-30, -44)
	_name_label.custom_minimum_size = Vector2(60, 0)
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_name_label.add_theme_font_size_override("font_size", 12)
	add_child(_name_label)

	_state_label = Label.new()
	_state_label.position = Vector2(-60, 36)
	_state_label.custom_minimum_size = Vector2(120, 0)
	_state_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_state_label.add_theme_font_size_override("font_size", 10)
	_state_label.add_theme_color_override("font_color", Color(0.92, 0.92, 0.8, 0.85))
	add_child(_state_label)

	_bubble = Label.new()
	_bubble.visible = false
	_bubble.position = Vector2(-90, -84)
	_bubble.custom_minimum_size = Vector2(180, 0)
	_bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble.add_theme_font_size_override("font_size", 13)
	_bubble.add_theme_color_override("font_color", Color(0.1, 0.1, 0.1))
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 0.98, 0.88, 0.92)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 8.0
	style.content_margin_right = 8.0
	style.content_margin_top = 4.0
	style.content_margin_bottom = 4.0
	_bubble.add_theme_stylebox_override("normal", style)
	add_child(_bubble)

	# M6：点击拾取区（圆形覆盖精灵），点村民打开其档案页
	var pick := Area2D.new()
	pick.input_pickable = true
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 14.0 * Config.CHAR_SCALE
	shape.shape = circle
	pick.add_child(shape)
	pick.input_event.connect(
		func(_vp: Node, ev: InputEvent, _idx: int) -> void:
			var mb := ev as InputEventMouseButton
			if mb != null and mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
				clicked.emit(npc_id))
	add_child(pick)


## 引擎确认的当前地点（供 main 判断是否需要重新分配锚点）
func current_place() -> String:
	return _place


## 快照驱动：地点变了 → 步行去新地点锚点；气泡/状态条更新
func apply_snapshot(info: Dictionary) -> void:
	var new_place := str(info.get("location", _place))
	if new_place != _place:
		_place = new_place
		_anchor = Config.anchor_of(_place, anchor_index)
		if position == Vector2.ZERO:
			position = _anchor          # 首帧直接落位，不演出生步行
			_state = State.WANDER
		else:
			_target = _anchor
			_state = State.WALKING      # 平滑步行过去（变速拍安全：move_toward）
	var bubble: Variant = info.get("bubble")
	if bubble != null and str(bubble) != "":
		_show_bubble(str(bubble))
	var cs := str(info.get("current_state", "")).strip_edges().replace("\n", " ")
	_state_label.text = ("〔%s〕" % cs.left(18)) if cs != "" else ""


func _process(delta: float) -> void:
	match _state:
		State.WALKING:
			_step_towards(_target, Config.NPC_SPEED, delta)
			if position.distance_to(_target) < 4.0:
				_state = State.WANDER
				_wander_timer = randf_range(2.0, 5.0)
		State.WANDER:
			_wander_timer -= delta
			if _wander_timer <= 0.0:
				_wander_timer = randf_range(3.0, 8.0)
				_target = _anchor + Vector2(
					randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS),
					randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS),
				)
			if position.distance_to(_target) > 4.0:
				_step_towards(_target, Config.NPC_SPEED * 0.45, delta)
			else:
				_play_idle()
		State.IDLE:
			_play_idle()
	if _bubble.visible:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			_bubble.visible = false


func _step_towards(target: Vector2, speed: float, delta: float) -> void:
	var before := position
	position = position.move_toward(target, speed * delta)
	var v := position - before
	if v.length_squared() > 0.01:
		_facing = SpriteLib.dir_name(v, _facing)
		_sprite.play("walk_%s" % _facing)
	else:
		_play_idle()


func _play_idle() -> void:
	_sprite.play("idle_%s" % _facing)


func _show_bubble(text: String) -> void:
	_bubble.text = text
	_bubble.visible = true
	_bubble_timer = Config.BUBBLE_SECONDS
