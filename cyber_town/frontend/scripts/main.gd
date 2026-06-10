extends Node2D
## 主场景编排：地面绘制 / NPC 生成 / 快照分发 / zone→request_move / HUD / BGM。
## 协议状态（confirmed_place / pending_move）由本脚本唯一持有（方案 §7.2）。

const PlayerScene := preload("res://scenes/player.tscn")
const NpcScene := preload("res://scenes/npc.tscn")

var player: CharacterBody2D
var day_night: CanvasModulate
var phone: CanvasLayer           # 类手机菜单（M3）
var _npcs := {}                  # npc_id(int) -> npc 节点
var _names := {}                 # agent_id(int) -> 显示名（hello 名册）

const E_TALK_DISTANCE := 96.0    # 按 E 直达私聊的触发距离（像素）
var _player_id := -1
var _confirmed_place := ""       # 引擎确认的玩家所在地
var _pending_move := ""          # 已发送、等下一拍确认的目标地
var _pending_since := 0.0        # pending 发出时刻（秒）——超时自愈用
var _anchor_counter := {}        # place_id -> 已分配锚点数

## 移动确认超时（秒）：引擎对非法 request_move 是静默丢弃（无失败回执），
## pending 超过此时长未被快照确认就自动清除，允许玩家重新触发（审查 PROTO-002）
const PENDING_TIMEOUT := 8.0

var _clock_label: Label
var _banner: Label
var _hint: Label


func _ready() -> void:
	_build_ground()
	_build_decor()
	# script.new()：从脚本直接实例化（脚本 extends CanvasModulate），
	# 比先 new 再 set_script 更符合 Godot 4 习惯且初始化时序无歧义
	day_night = (load("res://scripts/day_night.gd") as GDScript).new()
	add_child(day_night)

	player = PlayerScene.instantiate()
	player.position = Vector2(270, 380)  # farm 初始落位
	add_child(player)

	_build_hud()
	_build_bgm()

	phone = (load("res://scripts/phone_menu.gd") as GDScript).new()
	add_child(phone)
	# 发送即本地回显（D18：自己的当面说立即出气泡，不等快照）
	phone.speak_requested.connect(func(content: String) -> void:
		player.show_bubble(content))

	WorldNet.hello_received.connect(_on_hello)
	WorldNet.snapshot_received.connect(_on_snapshot)
	WorldNet.connection_changed.connect(_on_connection)


func _physics_process(_delta: float) -> void:
	_check_zone_transition()
	_update_talk_hint()


## 键盘热键（_unhandled：输入框打字时不触发）
func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_TAB:
			phone.toggle()
		KEY_ESCAPE:
			phone.close()
		KEY_E:
			if not phone.is_open():
				var npc_id := _nearest_npc_id()
				if npc_id >= 0:
					phone.open_private(npc_id)  # 按 E 直达该 NPC 私聊页（D9）


func _nearest_npc_id() -> int:
	var best := -1
	var best_d := E_TALK_DISTANCE
	for aid in _npcs:
		var d: float = player.position.distance_to(_npcs[aid].position)
		if d < best_d:
			best_d = d
			best = aid
	return best


func _update_talk_hint() -> void:
	var npc_id := _nearest_npc_id()
	if npc_id >= 0 and not phone.is_open():
		_hint.text = "按 E 和 %s 私聊 · Tab 打开小镇通" % str(_names.get(npc_id, "村民"))
	else:
		_hint.text = "WASD/方向键 走动 · 走进区域即可前往 · Tab 打开小镇通"


# ---- 协议侧 ----------------------------------------------------------------

func _on_hello(data: Dictionary) -> void:
	# 重连=全量重建：协议状态归零（NPC 节点保留复用，位置由快照重新驱动），
	# 否则锚点计数/pending 残留会造成站位漂移与卡死（审查 PROTO-001/003）
	_anchor_counter = {}
	_pending_move = ""
	_player_id = int(data.get("player_agent_id", 0))
	# 按名册建 NPC 节点（排除玩家）；位置等首帧快照落位
	var agents: Dictionary = data.get("agents", {})
	for aid_str in agents:
		var aid := int(aid_str)
		_names[aid] = str(agents[aid_str])
		if aid == _player_id or _npcs.has(aid):
			continue
		var npc := NpcScene.instantiate()
		npc.npc_id = aid
		npc.display_name = str(agents[aid_str])
		add_child(npc)
		_npcs[aid] = npc
	# 菜单名册/群信息
	phone.player_id = _player_id
	phone.names = _names
	phone.groups = data.get("groups", [])


func _on_snapshot(frame: Dictionary) -> void:
	var data: Dictionary = frame.get("data", {})
	# 世界时间 → HUD + 日夜
	var wt := str(data.get("world_time", ""))
	if wt != "":
		_clock_label.text = "🕐 %s" % wt
		day_night.set_world_time(wt)
	# agents 分发
	var agents: Dictionary = data.get("agents", {})
	for aid_str in agents:
		var aid := int(aid_str)
		var info: Dictionary = agents[aid_str]
		if aid == _player_id:
			_apply_player_state(info)
		elif _npcs.has(aid):
			# 给 NPC 分配该地点的到场锚点序号（首次出现在该地点时）
			var npc = _npcs[aid]
			var loc := str(info.get("location", ""))
			if loc != "" and npc.current_place() != loc:
				_anchor_counter[loc] = int(_anchor_counter.get(loc, 0)) + 1
				npc.anchor_index = _anchor_counter[loc]
			npc.apply_snapshot(info)
	# 菜单灌入消息流 + 当面说可用性（移动 pending 时置灰，方案 §7.2）
	phone.ingest_snapshot(data)
	var present: Array = []
	var places: Dictionary = data.get("places", {})
	if places.has(_confirmed_place):
		for oid in places[_confirmed_place].get("occupants", []):
			if int(oid) != _player_id:
				present.append(str(_names.get(int(oid), oid)))
	phone.set_local_enabled(_pending_move == "", present)


func _apply_player_state(info: Dictionary) -> void:
	var loc := str(info.get("location", ""))
	if loc == "":
		return
	_confirmed_place = loc
	if _pending_move != "" and loc == _pending_move:
		_pending_move = ""  # 移动已被引擎结算（拍末 commit）
	# 自己当面说的话：M3 接入发言 UI 时做「发送即本地回显」；
	# M2 阶段玩家尚无发言入口，这里仅以快照 bubble 兜底（外部注入的情形）
	var bubble: Variant = info.get("bubble")
	if bubble != null and str(bubble) != "":
		player.show_bubble(str(bubble))


func _on_connection(connected: bool) -> void:
	_banner.visible = not connected
	if not connected:
		_banner.text = "⚠ 与世界失去连接，重连中…"
		_pending_move = ""  # 断线撤销待确认移动（命令可能已丢，重连后可重发）


## zone 检测：玩家精灵走进新地点矩形 → 发 request_move（pending 期不重发、不回弹）。
## 触发判定用内缩矩形（滞后缓冲），避免边界来回闪烁重复触发（审查 PROTO-008）。
func _check_zone_transition() -> void:
	if player == null:
		return
	# pending 超时自愈：引擎静默丢弃非法移动时不会有回执
	if _pending_move != "" and (Time.get_ticks_msec() / 1000.0 - _pending_since) > PENDING_TIMEOUT:
		_pending_move = ""
	var zone := ""
	for pid in Config.ZONES:
		if (Config.ZONES[pid] as Rect2).grow(-14.0).has_point(player.position):
			zone = pid
			break
	if zone == "" or zone == _confirmed_place or zone == _pending_move:
		return
	if WorldNet.send_request_move(zone):
		_pending_move = zone
		_pending_since = Time.get_ticks_msec() / 1000.0


# ---- 表现层构建 -------------------------------------------------------------

func _build_ground() -> void:
	# 全图野地底色
	var base := ColorRect.new()
	base.color = Config.GRASS_BASE
	base.position = Config.WORLD_RECT.position
	base.size = Config.WORLD_RECT.size
	base.z_index = -20
	add_child(base)
	# 三个地点的地面块 + 名牌
	for pid in Config.ZONES:
		var rect: Rect2 = Config.ZONES[pid]
		var patch := ColorRect.new()
		patch.color = Config.ZONE_COLORS[pid]
		patch.position = rect.position
		patch.size = rect.size
		patch.z_index = -10
		add_child(patch)
		var border := ReferenceRect.new()
		border.position = rect.position
		border.size = rect.size
		border.border_color = Color(0, 0, 0, 0.25)
		border.border_width = 2.0
		border.editor_only = false
		border.z_index = -9
		add_child(border)
		var sign := Label.new()
		sign.text = "「%s」" % Config.ZONE_NAMES[pid]
		sign.position = rect.position + Vector2(rect.size.x / 2 - 36, -30)
		sign.add_theme_font_size_override("font_size", 18)
		sign.add_theme_color_override("font_color", Color(1, 1, 0.9))
		sign.z_index = -8
		add_child(sign)


func _build_decor() -> void:
	# 用 CC0 图集（Overworld.png）摆装饰物：谷仓/喷泉/集市摊/木屋/树/栅栏/木箱。
	# 全部 z_index=-5：压在地面色块(-10)之上、角色(0)之下，不参与碰撞。
	var atlas: Texture2D = load("res://assets/gfx/Overworld.png")
	for entry in Config.DECOR_PLACEMENTS:
		var region: Rect2 = Config.DECOR_REGIONS[entry[0]]
		var at := AtlasTexture.new()
		at.atlas = atlas
		at.region = region
		var sp := Sprite2D.new()
		sp.texture = at
		sp.scale = Vector2.ONE * Config.SPRITE_SCALE
		sp.position = entry[1]
		sp.z_index = -5
		add_child(sp)


func _build_hud() -> void:
	var ui := CanvasLayer.new()
	ui.name = "UI"
	add_child(ui)
	_clock_label = Label.new()
	_clock_label.position = Vector2(16, 12)
	_clock_label.add_theme_font_size_override("font_size", 20)
	ui.add_child(_clock_label)
	_banner = Label.new()
	_banner.visible = false
	_banner.position = Vector2(16, 44)
	_banner.add_theme_font_size_override("font_size", 14)
	_banner.add_theme_color_override("font_color", Color(1, 0.45, 0.4))
	ui.add_child(_banner)
	_hint = Label.new()
	_hint.text = "WASD/方向键 走动 · 走进区域即可前往 · Tab 打开小镇通"
	_hint.position = Vector2(16, 690)
	_hint.add_theme_font_size_override("font_size", 13)
	_hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.7))
	ui.add_child(_hint)


func _build_bgm() -> void:
	var bgm := AudioStreamPlayer.new()
	var stream: AudioStream = load("res://assets/audio/town_theme.mp3")
	if stream is AudioStreamMP3:
		(stream as AudioStreamMP3).loop = true
	bgm.stream = stream
	bgm.volume_db = -14.0
	bgm.autoplay = true
	add_child(bgm)
	bgm.play()
