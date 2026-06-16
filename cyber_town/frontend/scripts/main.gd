extends Node2D
## 主场景编排：地面绘制 / NPC 生成 / 快照分发 / zone→request_move / HUD / BGM。
## 协议状态（confirmed_place / pending_move）由本脚本唯一持有（方案 §7.2）。
##
## W7 画面升级（调研清单落地）：Y-sort 世界容器（角色可走到树/屋后）/
## 树墙封边 / 草路边界咬合 + 点缀分区 / 云影 / 夜晚暖色点光 + darkness 驱动 /
## 屏幕暗角 / 植被风摆 shader / 炊烟·萤火虫·樱花瓣粒子 / HUD pill 化去 emoji /
## 思考中指示接线。

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
var _event_label: Label          # W5 世界事件条幅
var _event_panel: PanelContainer
var _banner_panel: PanelContainer

# ---- W7 画面件 ----
var _world_ysort: Node2D         # Y-sort 容器：角色 + 大物件按脚底深度排序
var _lights: Array = []          # 夜晚暖色点光（darkness 驱动）
var _light_phases: Array = []    # 每盏火光抖动相位
var _vignette_mat: ShaderMaterial
var _cloud: Sprite2D             # 云影层
var _fireflies: CPUParticles2D
var _darkness := 0.0
var _wind_mat: ShaderMaterial    # 植被风摆共享材质

## 夜晚点光位（暖橘）：农舍门 / 杂货铺门 / 酒馆门两盏 / 鸟居
const LIGHT_SPOTS := [
	Vector2(180, 280), Vector2(930, 540),
	Vector2(1265, 310), Vector2(1335, 310), Vector2(620, 230),
]
## 参与风摆的植被物件
const SWAY_PROPS := ["tree_round", "pine", "bush", "sakura"]
## 需要垫脚下阴影的大物件
const SHADOW_PROPS := ["house_thatch", "house_door", "house_red", "house_dome",
	"tree_round", "pine", "bush", "sakura", "cart", "torii"]


func _ready() -> void:
	# Y-sort 世界容器（结构基础：阴影/风摆/遮挡都挂在这棵树下）
	_world_ysort = Node2D.new()
	_world_ysort.y_sort_enabled = true
	add_child(_world_ysort)

	_build_ground()
	_build_decor()
	_build_cloud_shadow()
	# script.new()：从脚本直接实例化（脚本 extends CanvasModulate），
	# 比先 new 再 set_script 更符合 Godot 4 习惯且初始化时序无歧义
	day_night = (load("res://scripts/day_night.gd") as GDScript).new()
	add_child(day_night)
	day_night.darkness_changed.connect(_on_darkness)

	player = PlayerScene.instantiate()
	player.position = Vector2(270, 404)  # farm 初始落位（脚底原点，y 下调半身）
	_world_ysort.add_child(player)

	_build_lights()
	_build_ambient_particles()
	_build_hud()
	_build_bgm()

	phone = (load("res://scripts/phone_menu.gd") as GDScript).new()
	add_child(phone)
	# 发送即本地回显（D18：自己的当面说立即出气泡，不等快照）
	phone.speak_requested.connect(func(content: String) -> void:
		player.show_bubble(content)
		var near := _nearest_npc_id()
		if near >= 0:
			_npcs[near].set_thinking(true))   # 在想怎么接话（W7 等待反馈）
	phone.dm_sent.connect(func(npc_id: int) -> void:
		if _npcs.has(npc_id):
			_npcs[npc_id].set_thinking(true))

	WorldNet.hello_received.connect(_on_hello)
	WorldNet.snapshot_received.connect(_on_snapshot)
	WorldNet.connection_changed.connect(_on_connection)


func _physics_process(_delta: float) -> void:
	_check_zone_transition()
	_update_talk_hint()


func _process(_delta: float) -> void:
	# 夜晚火光微抖（darkness=0 时灯灭，energy 抖动也为 0）
	if _darkness > 0.01:
		var ms := Time.get_ticks_msec()
		for i in _lights.size():
			var l: PointLight2D = _lights[i]
			l.energy = _darkness * 1.2 + sin(ms * 0.007 + float(_light_phases[i])) * 0.07 * _darkness
	# 云影缓慢飘动（夜里渐隐）
	if _cloud != null:
		_cloud.region_rect = Rect2(
			_cloud.region_rect.position + Vector2(12, 5) * _delta,
			_cloud.region_rect.size)
	_declutter_bubbles()


## W9 气泡去重堆叠：多个角色同屏说话时把重叠气泡垂直错开。收集本帧可见气泡
## 交给 SpriteLib.declutter_bubbles（核心算法抽离，便于确定性测试）。
func _declutter_bubbles() -> void:
	var owners: Array = []
	if player != null and player.bubble_visible():
		owners.append(player)
	for aid in _npcs:
		if _npcs[aid].bubble_visible():
			owners.append(_npcs[aid])
	SpriteLib.declutter_bubbles(owners)


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
		npc.clicked.connect(func(clicked_id: int) -> void:
			phone.open_profile(clicked_id))   # M6：点村民看档案
		_world_ysort.add_child(npc)
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
		_clock_label.text = wt
		day_night.set_world_time(wt)
	# W5 环境事件（世界事实，来自世界事件导演）
	var ev: Variant = data.get("world_event")
	if ev != null and str(ev) != "":
		_event_label.text = str(ev)
		_event_panel.visible = true
		# 风类事件 → 植被摆幅加倍（事实驱动的表现层联动）
		_wind_mat.set_shader_parameter("amp",
			3.2 if ("风" in str(ev) or "雨" in str(ev)) else 1.6)
	else:
		_event_panel.visible = false
		_wind_mat.set_shader_parameter("amp", 1.6)
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
	var bubble: Variant = info.get("bubble")
	if bubble != null and str(bubble) != "":
		player.show_bubble(str(bubble))


func _on_connection(connected: bool) -> void:
	_banner_panel.visible = not connected
	if not connected:
		_banner.text = "与世界失去连接，重连中…"
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

## 地面：TileMapLayer 程序化密铺（Ninja Adventure tileset，16px @×2 = 32px/格）。
## 草基底 + 广场橙砂 + 泥土小路；W7：草↔路边界叠草丛咬合、点缀密度分区。
func _build_ground() -> void:
	# 兜底背景色（防点缀 tile 透明边/任何缝隙透出 viewport 灰）
	var backdrop := ColorRect.new()
	backdrop.color = Color(0.58, 0.62, 0.40)
	backdrop.position = Config.WORLD_RECT.position - Vector2(64, 64)
	backdrop.size = Config.WORLD_RECT.size + Vector2(128, 128)
	backdrop.z_index = -30
	add_child(backdrop)

	var tile_set := TileSet.new()
	tile_set.tile_size = Vector2i(16, 16)
	var src := TileSetAtlasSource.new()
	src.texture = load(Config.NA_TILESET)
	src.texture_region_size = Vector2i(16, 16)
	# 注册地形家族全部用到的瓦片：草变体 + 泥中心 + 泥嵌草 3×3 块 9 格 + 点缀
	var used: Array = Config.T_GRASS.duplicate()
	used.append(Config.T_DIRT_CENTER)
	for dy in range(3):
		for dx in range(3):
			used.append(Config.T_DIRT_BLOCK + Vector2i(dx, dy))
	used.append_array(Config.T_DECO)
	for coord in used:
		if not src.has_tile(coord):
			src.create_tile(coord)
	tile_set.add_source(src, 0)

	# 双层：base 满铺（草基底 + autotile 泥过渡）；deco 稀疏点缀（草丛/花）
	var base := TileMapLayer.new()
	base.tile_set = tile_set
	base.scale = Vector2.ONE * Config.SPRITE_SCALE
	base.z_index = -20
	add_child(base)
	var deco := TileMapLayer.new()
	deco.tile_set = tile_set
	deco.scale = Vector2.ONE * Config.SPRITE_SCALE
	deco.z_index = -19
	add_child(deco)

	var cell_px := 16.0 * Config.SPRITE_SCALE
	var cols := int(Config.WORLD_RECT.size.x / cell_px) + 1
	var rows := int(Config.WORLD_RECT.size.y / cell_px) + 1
	var square: Rect2 = Config.ZONES["square"]
	var rng := RandomNumberGenerator.new()
	rng.seed = 20260610   # 固定种子：点缀分布稳定可截图回归

	# 第一遍：把每格分类为「夯土」(广场 + 小路) 或「草」，存进集合供 autotile 查邻居
	var is_dirt := {}
	for cy in rows:
		for cx in cols:
			var wpos := Vector2((cx + 0.5) * cell_px, (cy + 0.5) * cell_px)
			if square.has_point(wpos) or _on_path(wpos):
				is_dirt[Vector2i(cx, cy)] = true

	# 第二遍：草格铺基底+点缀；泥格用 bitmask 选 3×3 过渡块对应瓦片
	# （草是背景，块内位置由四邻是否为草决定——矩形/带状区域的角/边/内全覆盖）
	for cy in rows:
		for cx in cols:
			var cell := Vector2i(cx, cy)
			if is_dirt.has(cell):
				base.set_cell(cell, 0, _dirt_tile(is_dirt, cx, cy))
				continue
			var gi := 0 if rng.randf() < 0.78 else 1   # 草变体（主块为主，偶尔换口味）
			base.set_cell(cell, 0, Config.T_GRASS[gi])
			# 点缀分区：近路减半、野地加倍（打破均匀随机的程序感）
			var rate: float = Config.DECO_RATE
			var wy := (cy + 0.5) * cell_px
			if absf(wy - 430.0) < 90.0:
				rate *= 0.5
			elif wy < 160.0 or wy > 600.0:
				rate *= 1.6
			if rng.randf() < rate:
				deco.set_cell(cell, 0,
					Config.T_DECO[rng.randi_range(0, Config.T_DECO.size() - 1)])

	# 地点名牌（保留导航性；点阵字 12 整数倍防糊）
	for pid in Config.ZONES:
		var rect: Rect2 = Config.ZONES[pid]
		var sign := Label.new()
		sign.text = "「%s」" % Config.ZONE_NAMES[pid]
		sign.position = rect.position + Vector2(rect.size.x / 2 - 42, -34)
		sign.add_theme_font_size_override("font_size", 24)
		sign.add_theme_color_override("font_color", Color(1, 1, 0.92))
		sign.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
		sign.add_theme_constant_override("shadow_offset_y", 2)
		sign.z_index = -8
		add_child(sign)


## 横贯三区的泥土小路（带状，y 在 415±24 内蜿蜒）
func _on_path(wpos: Vector2) -> bool:
	if wpos.x < 90 or wpos.x > 1540:
		return false
	var wave := sin(wpos.x * 0.012) * 36.0
	return absf(wpos.y - (430.0 + wave)) < 26.0


## bitmask autotile：泥格按四邻是否为草，从 3×3「泥嵌草」块取对应过渡瓦片。
## 草在外侧 → 哪边是草哪边就用块的对应边/角；四邻皆泥=满泥中心。
## 矩形广场 + 横向小路均为凸形，9 格（4 角+4 边+中心）即可干净收边。
func _dirt_tile(is_dirt: Dictionary, cx: int, cy: int) -> Vector2i:
	var grass_up := not is_dirt.has(Vector2i(cx, cy - 1))
	var grass_down := not is_dirt.has(Vector2i(cx, cy + 1))
	var grass_left := not is_dirt.has(Vector2i(cx - 1, cy))
	var grass_right := not is_dirt.has(Vector2i(cx + 1, cy))
	if not (grass_up or grass_down or grass_left or grass_right):
		return Config.T_DIRT_CENTER
	var dx := 1   # 0 左边 / 1 中 / 2 右边
	if grass_left:
		dx = 0
	elif grass_right:
		dx = 2
	var dy := 1   # 0 上 / 1 中 / 2 下
	if grass_up:
		dy = 0
	elif grass_down:
		dy = 2
	return Config.T_DIRT_BLOCK + Vector2i(dx, dy)


func _build_decor() -> void:
	# Ninja Adventure 大块物件，全部挂 Y-sort 容器：排序原点移到脚底
	# （offset 上移半高 + position 下移半高 → 画面位置不变，人可走到物件后）
	var atlas: Texture2D = load(Config.NA_TILESET)
	_wind_mat = ShaderMaterial.new()
	_wind_mat.shader = _make_wind_shader()
	for entry in Config.NA_PLACEMENTS:
		_place_prop(atlas, entry[0], entry[1])
	_build_tree_wall(atlas)


func _place_prop(atlas: Texture2D, prop_name: String, center: Vector2) -> void:
	var region: Rect2 = Config.NA_PROPS[prop_name]
	var at := AtlasTexture.new()
	at.atlas = atlas
	at.region = region
	var sp := Sprite2D.new()
	sp.texture = at
	sp.scale = Vector2.ONE * Config.SPRITE_SCALE
	sp.offset = Vector2(0, -region.size.y / 2.0)
	sp.position = center + Vector2(0, region.size.y * Config.SPRITE_SCALE / 2.0)
	if prop_name in SWAY_PROPS:
		sp.material = _wind_mat            # 植被风摆（相位取世界 x，天然不同步）
	if prop_name in SHADOW_PROPS:
		var shadow := SpriteLib.make_shadow(region.size.x * 0.8)
		shadow.position = Vector2(0, -1)
		sp.add_child(shadow)               # 子节点随父参与同一 Y-sort 项
	_world_ysort.add_child(sp)


## 树墙封边：沿世界四边交错两排树，世界被森林包住（相机 limit 已内缩）
func _build_tree_wall(atlas: Texture2D) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 20260611
	var r := Config.WORLD_RECT
	var step := 52.0
	var x := r.position.x + 20.0
	while x < r.end.x:
		var kind := "pine" if rng.randf() < 0.6 else "tree_round"
		_place_prop(atlas, kind, Vector2(x + rng.randf_range(-10, 10), r.position.y + 4 + rng.randf_range(0, 14)))
		_place_prop(atlas, kind, Vector2(x + rng.randf_range(-10, 10), r.end.y - 18 + rng.randf_range(0, 12)))
		x += step
	var y := r.position.y + 40.0
	while y < r.end.y - 20.0:
		_place_prop(atlas, "pine", Vector2(r.position.x + 12 + rng.randf_range(0, 12), y))
		_place_prop(atlas, "tree_round" if rng.randf() < 0.4 else "pine",
			Vector2(r.end.x - 14 + rng.randf_range(-10, 0), y + 26.0))
		y += step
	# 泥路东侧断头处补灌木遮口
	_place_prop(atlas, "bush", Vector2(1556, 436))


## 植被风摆：顶点 shader，顶部摆动根部锚定；amp 由世界事件联动（风/雨加倍）
func _make_wind_shader() -> Shader:
	var sh := Shader.new()
	sh.code = """
shader_type canvas_item;
uniform float amp = 1.6;
void vertex() {
	float w = clamp(-VERTEX.y / 48.0, 0.0, 1.0);
	VERTEX.x += sin(TIME * 1.8 + MODEL_MATRIX[3][0] * 0.13) * amp * w;
}
"""
	return sh


## 云影：噪声黑斑层缓慢扫过地面（白天可见，夜里渐隐）
func _build_cloud_shadow() -> void:
	var noise := FastNoiseLite.new()
	noise.frequency = 0.012
	noise.seed = 7
	var src := noise.get_image(256, 256, false, false)   # 同步生成（web 单线程安全）
	var img := Image.create(256, 256, false, Image.FORMAT_RGBA8)
	for py in 256:
		for px in 256:
			var v := src.get_pixel(px, py).r          # 0..1 噪声
			img.set_pixel(px, py, Color(0, 0, 0, maxf(0.0, (0.55 - v)) * 0.4))
	_cloud = Sprite2D.new()
	_cloud.texture = ImageTexture.create_from_image(img)
	_cloud.centered = false
	_cloud.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	_cloud.region_enabled = true
	_cloud.region_rect = Rect2(Config.WORLD_RECT.position - Vector2(64, 64),
		Config.WORLD_RECT.size + Vector2(128, 128))
	_cloud.position = Config.WORLD_RECT.position - Vector2(64, 64)
	_cloud.scale = Vector2(2.0, 2.0)   # 噪声放大→云块更大更柔
	_cloud.z_index = -15               # 地面之上、Y-sort 角色之下
	add_child(_cloud)


## 夜晚暖色点光（农舍/杂货铺/酒馆门口/鸟居），darkness 驱动亮度
func _build_lights() -> void:
	var tex := SpriteLib.make_radial_tex(256, Color(1, 1, 1, 1), Color(1, 1, 1, 0))
	for spot in LIGHT_SPOTS:
		var l := PointLight2D.new()
		l.texture = tex
		l.color = Color(1.0, 0.78, 0.5)
		l.texture_scale = 2.5
		l.energy = 0.0
		l.position = spot
		add_child(l)
		_lights.append(l)
		_light_phases.append(randf() * TAU)


## 环境粒子：炊烟（常驻）/ 萤火虫（夜）/ 樱花瓣（常驻）
func _build_ambient_particles() -> void:
	# 农舍炊烟
	var smoke := SpriteLib.make_particles(8, 2.5)
	smoke.position = Vector2(196, 148)
	smoke.direction = Vector2(0, -1)
	smoke.gravity = Vector2(0, -8)
	smoke.initial_velocity_min = 4.0
	smoke.initial_velocity_max = 9.0
	smoke.scale_amount_min = 1.5
	smoke.scale_amount_max = 3.5
	smoke.spread = 12.0
	# color 与 color_ramp 双设：web Compatibility 下 ramp 偶发不生效（实测截图发黑），
	# color 是保底基色（ramp 生效时两者相乘，白 ramp × 浅灰 color 不变味）
	smoke.color = Color(0.93, 0.93, 0.93, 0.5)
	var smoke_ramp := Gradient.new()
	smoke_ramp.set_color(0, Color(1, 1, 1, 0.9))
	smoke_ramp.set_color(1, Color(1, 1, 1, 0.0))
	smoke.color_ramp = smoke_ramp
	smoke.z_index = 2
	add_child(smoke)
	# 池塘萤火虫（夜里出现）
	_fireflies = SpriteLib.make_particles(10, 3.0)
	_fireflies.position = Vector2(790, 280)
	_fireflies.emitting = false
	_fireflies.emission_shape = CPUParticles2D.EMISSION_SHAPE_SPHERE
	_fireflies.emission_sphere_radius = 90.0
	_fireflies.gravity = Vector2.ZERO
	_fireflies.initial_velocity_min = 2.0
	_fireflies.initial_velocity_max = 6.0
	_fireflies.scale_amount_min = 1.0
	_fireflies.scale_amount_max = 2.0
	_fireflies.color = Color(0.85, 1.0, 0.45, 0.85)
	var fly_ramp := Gradient.new()
	fly_ramp.add_point(0.5, Color(1, 1, 1, 1.0))
	fly_ramp.set_color(0, Color(1, 1, 1, 0.0))
	fly_ramp.set_color(2, Color(1, 1, 1, 0.0))
	_fireflies.color_ramp = fly_ramp
	_fireflies.z_index = 2
	add_child(_fireflies)
	# 樱花瓣（树冠下飘落）
	var petals := SpriteLib.make_particles(6, 2.2)
	petals.position = Vector2(870, 170)
	petals.emission_shape = CPUParticles2D.EMISSION_SHAPE_SPHERE
	petals.emission_sphere_radius = 30.0
	petals.direction = Vector2(0.3, 1)
	petals.gravity = Vector2(6, 14)
	petals.initial_velocity_min = 3.0
	petals.initial_velocity_max = 8.0
	petals.angular_velocity_min = -90.0
	petals.angular_velocity_max = 90.0
	petals.scale_amount_min = 1.5
	petals.scale_amount_max = 2.5
	petals.color = Color(1.0, 0.78, 0.86, 0.85)
	petals.z_index = 2
	add_child(petals)


## darkness（0=白昼 1=深夜）→ 点光/暗角/云影/萤火虫
func _on_darkness(d: float) -> void:
	_darkness = d
	for l in _lights:
		l.energy = d * 1.2
	if _vignette_mat != null:
		_vignette_mat.set_shader_parameter("intensity", lerpf(0.15, 0.35, d))
		_vignette_mat.set_shader_parameter("tint",
			Vector3(0.0, 0.0, 0.0).lerp(Vector3(0.05, 0.05, 0.12), d))
	if _cloud != null:
		_cloud.modulate.a = 1.0 - d        # 夜里没云影
	if _fireflies != null:
		_fireflies.emitting = d > 0.5


func _build_hud() -> void:
	var ui := CanvasLayer.new()
	ui.name = "UI"
	add_child(ui)

	# 屏幕暗角（昼轻夜重；第一个子节点，HUD 文字画在其上）
	var vig := ColorRect.new()
	vig.set_anchors_preset(Control.PRESET_FULL_RECT)
	vig.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_vignette_mat = ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = """
shader_type canvas_item;
uniform float intensity = 0.15;
uniform vec3 tint = vec3(0.0);
void fragment() {
	float d = length(UV - vec2(0.5));
	COLOR = vec4(tint, smoothstep(0.45, 0.95, d) * intensity);
}
"""
	_vignette_mat.shader = sh
	vig.material = _vignette_mat
	ui.add_child(vig)

	# 时钟（深色 pill，点阵字 24）
	var clock_panel := PanelContainer.new()
	clock_panel.add_theme_stylebox_override("panel", SpriteLib.make_panel_style())
	clock_panel.position = Vector2(16, 12)
	_clock_label = Label.new()
	_clock_label.add_theme_font_size_override("font_size", 24)
	clock_panel.add_child(_clock_label)
	ui.add_child(clock_panel)

	# 世界事件条幅
	_event_panel = PanelContainer.new()
	_event_panel.add_theme_stylebox_override("panel",
		SpriteLib.make_panel_style(Color(0.12, 0.2, 0.08, 0.55)))
	_event_panel.position = Vector2(110, 16)
	_event_panel.visible = false
	_event_label = Label.new()
	_event_label.add_theme_font_size_override("font_size", 12)
	_event_label.add_theme_color_override("font_color", Color(0.85, 0.95, 0.75))
	_event_panel.add_child(_event_label)
	ui.add_child(_event_panel)

	# 断线横幅
	_banner_panel = PanelContainer.new()
	_banner_panel.add_theme_stylebox_override("panel",
		SpriteLib.make_panel_style(Color(0.3, 0.05, 0.05, 0.6)))
	_banner_panel.position = Vector2(16, 52)
	_banner_panel.visible = false
	_banner = Label.new()
	_banner.add_theme_font_size_override("font_size", 12)
	_banner.add_theme_color_override("font_color", Color(1, 0.6, 0.55))
	_banner_panel.add_child(_banner)
	ui.add_child(_banner_panel)

	# 底部操作提示
	var hint_panel := PanelContainer.new()
	hint_panel.add_theme_stylebox_override("panel",
		SpriteLib.make_panel_style(Color(0, 0, 0, 0.35)))
	hint_panel.position = Vector2(16, 686)
	_hint = Label.new()
	_hint.text = "WASD/方向键 走动 · 走进区域即可前往 · Tab 打开小镇通"
	_hint.add_theme_font_size_override("font_size", 12)
	_hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.75))
	hint_panel.add_child(_hint)
	ui.add_child(hint_panel)


func _build_bgm() -> void:
	var bgm := AudioStreamPlayer.new()
	var stream: AudioStream = load("res://assets/audio/theme_village.ogg")
	if stream is AudioStreamOggVorbis:
		(stream as AudioStreamOggVorbis).loop = true
	bgm.stream = stream
	bgm.volume_db = -14.0
	bgm.autoplay = true
	add_child(bgm)
	bgm.play()
