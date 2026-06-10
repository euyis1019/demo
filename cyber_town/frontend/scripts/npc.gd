extends Node2D
## 村民 NPC 表现层：跨地点平滑步行（WALKING）+ 锚点游走（WANDER）+
## 头顶气泡/名牌/状态徽章。引擎态只有离散 place；坐标/动画全为前端推断（方案 §7.3）。
## 用 position 插值，不走物理（避免与玩家推挤）。
##
## W7 画面升级：节点原点=脚底（Y-sort 遮挡）/ 脚下软阴影 / 名牌 pill+主题色点 /
## 单字状态徽章（Smallville pronunciatio 思路，wasm 无 emoji 字体故用汉字）/
## 思考中「…」指示 / 气泡尾巴+Q 弹+打字机+淡出 / idle 呼吸 / 走路扬尘。

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
var _bubble_wrap: Node2D
var _bubble: Label
var _bubble_timer := 0.0
var _badge: PanelContainer
var _badge_label: Label
var _thinking: Label
var _dust: CPUParticles2D
var _wander_allowed := false     # W3 状态驱动：current_state 含动态语义才游走

## 动态语义词（NPC 自己写的 current_state 含这些字 → 它在「活动」→ 允许游走）；
## 静态语义（坐/蹲/靠/睡…）或无线索 → 站定。游走从此有 LLM 表达背书。
const ACTIVE_HINTS := ["走", "逛", "转", "巡", "跑", "忙", "干活", "收拾",
	"打扫", "理货", "搬", "摆", "备", "擦", "扫", "锄", "浇", "喂", "翻地", "薅"]
const STILL_HINTS := ["坐", "蹲", "靠", "躺", "歇", "睡", "发呆", "站定", "等着"]

## current_state 关键词 → 单字状态徽章（一眼看懂谁在干嘛；无匹配则隐藏）
const BADGE_RULES := [
	[["睡", "打盹", "眯", "梦"], "眠"],
	[["锄", "浇", "喂", "翻地", "薅", "种", "摘", "犁"], "农"],
	[["吃", "喝", "饭", "茶", "酒", "嚼"], "食"],
	[["聊", "唠", "说", "搭话", "招呼"], "聊"],
	[["坐", "靠", "歇", "晒", "发呆", "乘凉"], "歇"],
	[["扫", "擦", "理货", "收拾", "搬", "摆", "备", "忙", "洗"], "忙"],
	[["走", "逛", "巡", "转", "去"], "行"],
]


func _ready() -> void:
	# 按 agent_id 取专属村民外观（老钱=白须老者/阿香=紫发女/大山=橙衣壮汉）
	var tex_path: String = Config.NA_CHARS.get(npc_id, Config.NA_CHARS[3])
	var tex: Texture2D = load(tex_path)
	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = SpriteLib.build(tex)
	_sprite.scale = Vector2.ONE * Config.CHAR_SCALE
	# W7 Y-sort：图像上移半帧 → 节点原点落在脚底（排序参考点）
	_sprite.offset = Vector2(0, -8)
	_sprite.play("idle_down")
	add_child(_sprite)

	# 脚下软阴影
	var shadow := SpriteLib.make_shadow(26.0)
	shadow.position = Vector2(0, -2)
	add_child(shadow)

	# 名牌：深色 pill + 主题色圆点（草地上也看得清）
	var theme_color: Color = Config.NPC_COLORS.get(npc_id, Color.WHITE)
	var name_panel := PanelContainer.new()
	name_panel.add_theme_stylebox_override("panel", SpriteLib.make_panel_style())
	name_panel.position = Vector2(-36, -70)
	name_panel.custom_minimum_size = Vector2(72, 0)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	var dot := ColorRect.new()
	dot.color = theme_color
	dot.custom_minimum_size = Vector2(8, 8)
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(dot)
	var name_label := Label.new()
	name_label.text = display_name
	name_label.add_theme_font_size_override("font_size", 12)
	row.add_child(name_label)
	name_panel.add_child(row)
	add_child(name_panel)

	# 单字状态徽章（白底小圆 pill，名牌上方；变化时 Q 弹）
	_badge = PanelContainer.new()
	var badge_style := SpriteLib.make_panel_style(Color(1, 1, 1, 0.9))
	badge_style.corner_radius_top_left = 10
	badge_style.corner_radius_top_right = 10
	badge_style.corner_radius_bottom_left = 10
	badge_style.corner_radius_bottom_right = 10
	_badge.add_theme_stylebox_override("panel", badge_style)
	_badge.position = Vector2(14, -94)
	_badge.visible = false
	_badge_label = Label.new()
	_badge_label.add_theme_font_size_override("font_size", 12)
	_badge_label.add_theme_color_override("font_color", Color(0.25, 0.2, 0.1))
	_badge.add_child(_badge_label)
	add_child(_badge)

	# 思考中「…」（玩家发言→NPC 回拍之间的等待反馈，纯前端推断）
	_thinking = Label.new()
	_thinking.text = "…"
	_thinking.visible = false
	_thinking.position = Vector2(-6, -96)
	_thinking.add_theme_font_size_override("font_size", 24)
	_thinking.add_theme_color_override("font_color", Color(1, 1, 1, 0.9))
	_thinking.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.5))
	add_child(_thinking)

	_build_bubble()

	# 走路扬尘（脚下，仅移动时发射）
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

	# idle 呼吸微动效（NPC 常发呆，纵向 3% 呼吸让贴图「活着」；
	# 原点在脚底，缩放向上拉伸、脚不动）
	var breath := create_tween().set_loops()
	breath.tween_property(_sprite, "scale:y", Config.CHAR_SCALE * 1.03, 0.9) \
		.set_trans(Tween.TRANS_SINE)
	breath.tween_property(_sprite, "scale:y", Config.CHAR_SCALE * 1.0, 0.9) \
		.set_trans(Tween.TRANS_SINE)

	# M6：点击拾取区（圆形覆盖精灵），点村民打开其档案页
	var pick := Area2D.new()
	pick.input_pickable = true
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 14.0 * Config.CHAR_SCALE
	shape.shape = circle
	shape.position = Vector2(0, -24)   # 原点在脚底，拾取圆心上移到身体
	pick.add_child(shape)
	pick.input_event.connect(
		func(_vp: Node, ev: InputEvent, _idx: int) -> void:
			var mb := ev as InputEventMouseButton
			if mb != null and mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
				clicked.emit(npc_id))
	add_child(pick)


## 气泡三层结构：wrap（pivot 在尾巴根）+ Label + 尾巴 Polygon2D（主题色描边）
func _build_bubble() -> void:
	_bubble_wrap = Node2D.new()
	_bubble_wrap.visible = false
	_bubble_wrap.position = Vector2(0, -76)
	var theme_color: Color = Config.NPC_COLORS.get(npc_id, Color.WHITE)
	_bubble = Label.new()
	_bubble.position = Vector2(-90, -52)
	_bubble.custom_minimum_size = Vector2(180, 0)
	_bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_bubble.add_theme_font_size_override("font_size", 12)
	_bubble.add_theme_color_override("font_color", Color(0.1, 0.1, 0.1))
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 0.98, 0.88, 0.94)
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
	# 尾巴：指向说话人的小三角（贴气泡底沿中点）
	var tail := Polygon2D.new()
	tail.polygon = PackedVector2Array([Vector2(-6, -2), Vector2(6, -2), Vector2(0, 8)])
	tail.color = theme_color
	_bubble_wrap.add_child(tail)
	add_child(_bubble_wrap)


## 引擎确认的当前地点（供 main 判断是否需要重新分配锚点）
func current_place() -> String:
	return _place


## 快照驱动：地点变了 → 步行去新地点锚点；气泡/徽章更新
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
	_apply_badge(cs)
	_wander_allowed = _infer_wander(cs)


## current_state → 单字徽章（变化时 Q 弹放大）
func _apply_badge(cs: String) -> void:
	var glyph := ""
	if cs != "":
		for rule in BADGE_RULES:
			for w in rule[0]:
				if cs.contains(w):
					glyph = rule[1]
					break
			if glyph != "":
				break
	if glyph == "":
		_badge.visible = false
		return
	if _badge.visible and _badge_label.text == glyph:
		return
	_badge_label.text = glyph
	_badge.visible = true
	_badge.scale = Vector2(0.6, 0.6)
	var tw := _badge.create_tween()
	tw.tween_property(_badge, "scale", Vector2.ONE, 0.22) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


## 思考中指示（main 在玩家发言后置 true；出气泡时自动清除）
func set_thinking(on: bool) -> void:
	if _thinking.visible == on:
		return
	_thinking.visible = on
	if on:
		var tw := _thinking.create_tween().set_loops()
		tw.tween_property(_thinking, "modulate:a", 0.4, 0.5)
		tw.tween_property(_thinking, "modulate:a", 1.0, 0.5)


func _process(delta: float) -> void:
	var moving := false
	match _state:
		State.WALKING:
			moving = _step_towards(_target, Config.NPC_SPEED, delta)
			if position.distance_to(_target) < 4.0:
				_state = State.WANDER
				_wander_timer = randf_range(2.0, 5.0)
		State.WANDER:
			# W3：仅当 NPC 自己的 current_state 表达了动态语义才游走
			# （干活/打扫/理货…）；否则站定播 idle——画面不杜撰行为
			if not _wander_allowed:
				_play_idle()
			else:
				_wander_timer -= delta
				if _wander_timer <= 0.0:
					_wander_timer = randf_range(3.0, 8.0)
					_target = _anchor + Vector2(
						randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS),
						randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS),
					)
				if position.distance_to(_target) > 4.0:
					moving = _step_towards(_target, Config.NPC_SPEED * 0.45, delta)
				else:
					_play_idle()
		State.IDLE:
			_play_idle()
	_dust.emitting = moving
	if _bubble_wrap.visible and _bubble_timer > 0.0:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			SpriteLib.fade_bubble(_bubble_wrap)


func _step_towards(target: Vector2, speed: float, delta: float) -> bool:
	var before := position
	position = position.move_toward(target, speed * delta)
	var v := position - before
	if v.length_squared() > 0.01:
		_facing = SpriteLib.dir_name(v, _facing)
		_sprite.play("walk_%s" % _facing)
		return true
	_play_idle()
	return false


## W3 状态驱动游走判定：静态语义（明确「不动」）优先压制；其次动态语义放行；
## 两者皆无 → 站定（保守：没有 LLM 表达背书就不杜撰走动）。
func _infer_wander(cs: String) -> bool:
	for w in STILL_HINTS:
		if cs.contains(w):
			return false
	for w in ACTIVE_HINTS:
		if cs.contains(w):
			return true
	return false


func _play_idle() -> void:
	_sprite.play("idle_%s" % _facing)


func _show_bubble(text: String) -> void:
	set_thinking(false)
	_bubble.text = text
	_bubble_timer = Config.BUBBLE_SECONDS
	SpriteLib.pop_bubble(_bubble_wrap, _bubble)
