extends Node3D
## 村民 NPC（3D）：引擎态只有离散 place，坐标/动画全前端推断。地点变 → 走去新地点
## 锚点；按 current_state 语义决定是否游走（不杜撰行为）；头顶名牌/气泡/状态徽章/思考指示
## 均用 billboard Label3D。点击打开档案。

signal clicked(npc_id: int)

var npc_id: int = -1
var display_name := ""
var anchor_index := 0

enum State { IDLE, WANDER, WALKING }
var _state: State = State.IDLE
var _place := ""
var _anchor := Vector2.ZERO       # 当前地点锚点（XZ）
var _target := Vector2.ZERO
var _wander_timer := 0.0
var _facing := "down"
var _wander_allowed := false

var _spr: AnimatedSprite3D
var _name: Label3D
var _badge: Label3D
var _bubble: Label3D
var _think: Label3D
var _bubble_timer := 0.0

const ACTIVE_HINTS := ["走", "逛", "转", "巡", "跑", "忙", "干活", "收拾",
	"打扫", "理货", "搬", "摆", "备", "擦", "扫", "锄", "浇", "喂", "翻地", "薅"]
const STILL_HINTS := ["坐", "蹲", "靠", "躺", "歇", "睡", "发呆", "站定", "等着"]
const BADGE_RULES := [
	[["睡", "打盹", "眯", "梦"], "眠"], [["锄", "浇", "喂", "翻地", "薅", "种", "摘", "犁"], "农"],
	[["吃", "喝", "饭", "茶", "酒", "嚼"], "食"], [["聊", "唠", "说", "搭话", "招呼"], "聊"],
	[["坐", "靠", "歇", "晒", "发呆", "乘凉"], "歇"],
	[["扫", "擦", "理货", "收拾", "搬", "摆", "备", "忙", "洗"], "忙"],
	[["走", "逛", "巡", "转", "去"], "行"],
]


func _ready() -> void:
	var theme: Color = Config.NPC_COLORS.get(npc_id, Color.WHITE)
	_spr = SpriteLib3D.make_char_sprite(load(Config.CHARS.get(npc_id, Config.CHARS[3])), Config.CHAR_PX)
	add_child(_spr)
	add_child(SpriteLib3D.make_blob(load(Config.T_BLOB), 0.5))

	_name = SpriteLib3D.make_label(48, theme)
	_name.text = display_name
	_name.position = Vector3(0, 2.0, 0)
	add_child(_name)

	_badge = SpriteLib3D.make_label(56, Color(1, 1, 1))
	_badge.position = Vector3(0, 2.45, 0)
	_badge.visible = false
	add_child(_badge)

	_bubble = SpriteLib3D.make_label(44, Color(1, 0.98, 0.86))
	_bubble.position = Vector3(0, 2.6, 0)
	_bubble.width = 600
	_bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble.visible = false
	add_child(_bubble)

	_think = SpriteLib3D.make_label(60, Color(1, 1, 1))
	_think.text = "…"
	_think.position = Vector3(0, 2.5, 0)
	_think.visible = false
	add_child(_think)

	# 点击拾取（Area3D + 摄像机射线 picking）
	var area := Area3D.new()
	area.input_ray_pickable = true
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.6
	cap.height = 1.8
	cs.shape = cap
	cs.position = Vector3(0, 0.9, 0)
	area.add_child(cs)
	area.input_event.connect(func(_c: Node, ev: InputEvent, _p: Vector3, _n: Vector3, _i: int) -> void:
		var mb := ev as InputEventMouseButton
		if mb != null and mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			clicked.emit(npc_id))
	add_child(area)


func current_place() -> String:
	return _place


## 快照驱动：地点变 → 走去新锚点；气泡/徽章/游走许可更新
func apply_snapshot(info: Dictionary) -> void:
	var new_place := str(info.get("location", _place))
	if new_place != _place:
		_place = new_place
		_anchor = Config.anchor_of(_place, anchor_index)
		if position == Vector3.ZERO:
			_warp_to(_anchor)
			_state = State.WANDER
		else:
			_target = _anchor
			_state = State.WALKING
	var bubble: Variant = info.get("bubble")
	if bubble != null and str(bubble) != "":
		_show_bubble(str(bubble))
	var cs := str(info.get("current_state", "")).strip_edges().replace("\n", " ")
	_apply_badge(cs)
	_wander_allowed = _infer_wander(cs)


func set_thinking(on: bool) -> void:
	if _think.visible == on:
		return
	_think.visible = on


func _process(delta: float) -> void:
	match _state:
		State.WALKING:
			if _step_towards(_target, Config.NPC_SPEED, delta):
				pass
			if _xz().distance_to(_target) < 0.3:
				_state = State.WANDER
				_wander_timer = randf_range(2.0, 5.0)
		State.WANDER:
			if not _wander_allowed:
				_play_idle()
			else:
				_wander_timer -= delta
				if _wander_timer <= 0.0:
					_wander_timer = randf_range(3.0, 8.0)
					_target = _anchor + Vector2(
						randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS),
						randf_range(-Config.NPC_WANDER_RADIUS, Config.NPC_WANDER_RADIUS))
				if _xz().distance_to(_target) > 0.3:
					_step_towards(_target, Config.NPC_SPEED * 0.5, delta)
				else:
					_play_idle()
		State.IDLE:
			_play_idle()
	if _bubble.visible:
		_bubble_timer -= delta
		if _bubble_timer <= 0.0:
			_bubble.visible = false


func _xz() -> Vector2:
	return Vector2(position.x, position.z)


func _warp_to(xz: Vector2) -> void:
	position = Vector3(xz.x, Config.ground_y(xz), xz.y)


func _step_towards(target: Vector2, speed: float, delta: float) -> bool:
	var cur := _xz()
	var nx := cur.move_toward(target, speed * delta)
	var v := nx - cur
	position = Vector3(nx.x, Config.ground_y(nx), nx.y)
	if v.length_squared() > 0.000001:
		_facing = SpriteLib3D.dir_name(v, _facing)
		_spr.play("walk_%s" % _facing)
		return true
	_play_idle()
	return false


func _play_idle() -> void:
	_spr.play("idle_%s" % _facing)


func _infer_wander(cs: String) -> bool:
	for w in STILL_HINTS:
		if cs.contains(w):
			return false
	for w in ACTIVE_HINTS:
		if cs.contains(w):
			return true
	return false


func _apply_badge(cs: String) -> void:
	var glyph := ""
	if cs != "":
		for rule in BADGE_RULES:
			for w in rule[0]:
				if cs.contains(w):
					glyph = rule[1]; break
			if glyph != "":
				break
	_badge.visible = glyph != ""
	if glyph != "":
		_badge.text = glyph


func _show_bubble(text: String) -> void:
	set_thinking(false)
	var shown := text
	if shown.length() > 40:
		shown = shown.substr(0, 40) + "…"
	_bubble.text = shown
	_bubble.visible = true
	_bubble_timer = Config.BUBBLE_SECONDS
