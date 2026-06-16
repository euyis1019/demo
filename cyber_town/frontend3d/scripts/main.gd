extends Node3D
## 3D 主场景：全 3D 静态世界（地形/草/花/石/栅/菜畦）+ 快照驱动的玩家/NPC（billboard）
## + zone→request_move + 正交相机跟随 + 昼夜光 + HUD + 手机菜单。后端/WS 协议零改动，
## 仅把后端逻辑坐标映射到 XZ 平面（Config 负责布局与 ground_y）。

const PlayerScene := preload("res://scenes/player.tscn")
const NpcScene := preload("res://scenes/npc.tscn")

var player: Node3D
var _cam: Camera3D
var _sun: DirectionalLight3D
var phone: CanvasLayer
var _npcs := {}                  # npc_id -> npc 节点
var _names := {}                 # agent_id -> 显示名
var _player_id := -1
var _confirmed_place := ""
var _pending_move := ""
var _pending_since := 0.0
var _anchor_counter := {}
const PENDING_TIMEOUT := 8.0

var _beds: Array[Rect2] = []
var _wind_mat: ShaderMaterial

# HUD
var _clock: Label
var _event: Label
var _hint: Label
var _banner: Label


func _ready() -> void:
	_define_beds()
	_build_env()
	_build_terrain()
	_build_beds()
	_build_grass()
	_build_flowers()
	_build_rocks()
	_build_fences()
	_build_props()

	player = PlayerScene.instantiate()
	var sp := Config.PLAYER_SPAWN
	player.position = Vector3(sp.x, Config.ground_y(sp), sp.y)
	add_child(player)

	_cam = Camera3D.new()
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	_cam.size = Config.CAM_SIZE
	_cam.current = true
	add_child(_cam)
	_update_cam()

	_build_hud()
	_build_bgm()

	phone = (load("res://scripts/phone_menu.gd") as GDScript).new()
	add_child(phone)
	phone.speak_requested.connect(func(content: String) -> void:
		player.show_bubble(content)
		var nid := _nearest_npc_id()
		if nid >= 0:
			_npcs[nid].set_thinking(true))
	phone.dm_sent.connect(func(nid: int) -> void:
		if _npcs.has(nid):
			_npcs[nid].set_thinking(true))

	WorldNet.hello_received.connect(_on_hello)
	WorldNet.snapshot_received.connect(_on_snapshot)
	WorldNet.connection_changed.connect(_on_connection)


func _process(delta: float) -> void:
	_update_cam()
	_check_zone_transition()
	_update_hint()


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
				var nid := _nearest_npc_id()
				if nid >= 0:
					phone.open_private(nid)


# ---- 相机 / 提示 ---------------------------------------------------------

func _update_cam() -> void:
	if player == null:
		return
	_cam.position = player.position + Vector3(0, 16, 13)
	_cam.look_at(player.position + Vector3(0, 0.6, 0), Vector3.UP)


func _nearest_npc_id() -> int:
	var best := -1
	var bd := Config.E_TALK_DISTANCE
	for aid in _npcs:
		var d: float = player.position.distance_to(_npcs[aid].position)
		if d < bd:
			bd = d; best = aid
	return best


func _update_hint() -> void:
	var nid := _nearest_npc_id()
	if nid >= 0 and not phone.is_open():
		_hint.text = "按 E 和 %s 私聊 · Tab 打开小镇通" % str(_names.get(nid, "村民"))
	else:
		_hint.text = "WASD/方向键 走动 · 走进区域即可前往 · Tab 打开小镇通"


# ---- 协议侧 --------------------------------------------------------------

func _on_hello(data: Dictionary) -> void:
	_anchor_counter = {}
	_pending_move = ""
	_player_id = int(data.get("player_agent_id", 0))
	var agents: Dictionary = data.get("agents", {})
	for aid_str in agents:
		var aid := int(aid_str)
		_names[aid] = str(agents[aid_str])
		if aid == _player_id or _npcs.has(aid):
			continue
		var npc := NpcScene.instantiate()
		npc.npc_id = aid
		npc.display_name = str(agents[aid_str])
		npc.clicked.connect(func(cid: int) -> void: phone.open_profile(cid))
		add_child(npc)
		_npcs[aid] = npc
	phone.player_id = _player_id
	phone.names = _names
	phone.groups = data.get("groups", [])


func _on_snapshot(frame: Dictionary) -> void:
	var data: Dictionary = frame.get("data", {})
	var wt := str(data.get("world_time", ""))
	if wt != "":
		_clock.text = "🕐 " + wt
		_apply_daynight(wt)
	var ev: Variant = data.get("world_event")
	if ev != null and str(ev) != "":
		_event.text = "🍃 " + str(ev)
		_event.visible = true
		if _wind_mat != null:
			_wind_mat.set_shader_parameter("wind_strength",
				0.32 if ("风" in str(ev) or "雨" in str(ev)) else 0.18)
	else:
		_event.visible = false

	var agents: Dictionary = data.get("agents", {})
	for aid_str in agents:
		var aid := int(aid_str)
		var info: Dictionary = agents[aid_str]
		if aid == _player_id:
			_apply_player_state(info)
		elif _npcs.has(aid):
			var npc = _npcs[aid]
			var loc := str(info.get("location", ""))
			if loc != "" and npc.current_place() != loc:
				_anchor_counter[loc] = int(_anchor_counter.get(loc, 0)) + 1
				npc.anchor_index = _anchor_counter[loc]
			npc.apply_snapshot(info)

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
		_pending_move = ""
	var bubble: Variant = info.get("bubble")
	if bubble != null and str(bubble) != "":
		player.show_bubble(str(bubble))


func _on_connection(connected: bool) -> void:
	_banner.visible = not connected
	if not connected:
		_banner.text = "⚠ 与世界失去连接，重连中…"
		_pending_move = ""


func _check_zone_transition() -> void:
	if player == null:
		return
	if _pending_move != "" and (Time.get_ticks_msec() / 1000.0 - _pending_since) > PENDING_TIMEOUT:
		_pending_move = ""
	var xz := Vector2(player.position.x, player.position.z)
	var zone := Config.place_at(xz, 2.0)
	if zone == "" or zone == _confirmed_place or zone == _pending_move:
		return
	if WorldNet.send_request_move(zone):
		_pending_move = zone
		_pending_since = Time.get_ticks_msec() / 1000.0


# ---- 世界生成（全 3D）----------------------------------------------------

func _define_beds() -> void:
	for row in 3:
		_beds.append(Rect2(-36.0, -7.0 + row * 5.0, 12.0, 2.6))   # farm 菜畦


func _build_env() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_horizon_color = Color(0.75, 0.85, 0.95)
	sm.sky_top_color = Color(0.45, 0.7, 1.0)
	sm.ground_horizon_color = Color(0.62, 0.7, 0.55)
	sky.sky_material = sm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.6
	we.environment = env
	add_child(we)
	_sun = DirectionalLight3D.new()
	_sun.rotation_degrees = Vector3(-55, -50, 0)
	_sun.light_energy = 1.1
	_sun.light_color = Color(1.0, 0.96, 0.86)
	_sun.shadow_enabled = true
	_sun.directional_shadow_max_distance = 40.0
	add_child(_sun)


func _build_terrain() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var x0i := int(Config.WORLD.position.x)
	var z0i := int(Config.WORLD.position.y)
	var x1i := int(Config.WORLD.end.x)
	var z1i := int(Config.WORLD.end.y)
	for cz in range(z0i, z1i):
		for cx in range(x0i, x1i):
			_tv(st, cx, cz); _tv(st, cx + 1, cz); _tv(st, cx + 1, cz + 1)
			_tv(st, cx, cz); _tv(st, cx + 1, cz + 1); _tv(st, cx, cz + 1)
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = SpriteLib3D.terrain_mat(load(Config.T_GRASS), load(Config.T_DIRT))
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


func _tv(st: SurfaceTool, x: int, z: int) -> void:
	st.set_color(_splat(x, z))
	st.set_uv(Vector2(x, z))
	st.add_vertex(Vector3(x, Config.height(x, z), z))


func _splat(x: float, z: float) -> Color:
	var d := 0.0
	# 广场圆盘
	d = max(d, smoothstep(9.0, 6.0, Vector2(x, z).distance_to(Config.PLACE_CENTER["square"])))
	# 横贯小路（z≈0）
	if x > -40.0 and x < 40.0:
		d = max(d, smoothstep(2.4, 1.1, absf(z)))
	# 菜畦
	for b in _beds:
		if b.grow(0.6).has_point(Vector2(x, z)):
			d = max(d, 0.85)
	return Color(1.0 - d, d, 0.0)


func _in_skip(x: float, z: float) -> bool:
	# 草/花/石散点跳过：广场、路、菜畦
	if Vector2(x, z).distance_to(Config.PLACE_CENTER["square"]) < 8.0:
		return true
	if absf(z) < 2.2:
		return true
	for b in _beds:
		if b.has_point(Vector2(x, z)):
			return true
	return false


func _build_beds() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = load(Config.T_DIRT)
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	mat.uv1_scale = Vector3(4, 2, 1)
	for b in _beds:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(b.size.x, 0.22, b.size.y)
		mi.mesh = bm
		var c := b.get_center()
		mi.position = Vector3(c.x, Config.ground_y(c) + 0.02, c.y)
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		add_child(mi)


func _build_grass() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 20260616
	var src_t := SpriteLib3D.cross_quad(0.7, 0.75)
	_wind_mat = SpriteLib3D.grass_wind_mat(load(Config.T_TUFT))
	var src_b := SpriteLib3D.cross_quad(0.6, 0.95)
	var mat_b := SpriteLib3D.grass_wind_mat(load(Config.T_BLADE))
	var chunk := 11.0
	var wx := Config.WORLD.position.x
	var wz := Config.WORLD.position.y
	var nx := int(Config.WORLD.size.x / chunk) + 1
	var nz := int(Config.WORLD.size.y / chunk) + 1
	for cz in nz:
		for cx in nx:
			var ox := wx + cx * chunk
			var oz := wz + cz * chunk
			_grass_chunk(src_t, _wind_mat, ox, oz, chunk, 38, rng)
			_grass_chunk(src_b, mat_b, ox, oz, chunk, 22, rng)


func _grass_chunk(src: ArrayMesh, mat: Material, ox: float, oz: float,
		size: float, count: int, rng: RandomNumberGenerator) -> void:
	var tf: Array[Transform3D] = []
	for _i in count:
		var x := ox + rng.randf() * size
		var z := oz + rng.randf() * size
		if not Config.WORLD.has_point(Vector2(x, z)) or _in_skip(x, z):
			continue
		var b := Basis().rotated(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.7, 1.3))
		tf.append(Transform3D(b, Vector3(x, Config.ground_y(Vector2(x, z)), z)))
	if tf.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = src
	mm.instance_count = tf.size()
	for i in tf.size():
		mm.set_instance_transform(i, tf[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mmi)


func _build_flowers() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 777
	for fp in Config.FLOWERS:
		var src := SpriteLib3D.cross_quad(0.5, 0.7)
		var mat := SpriteLib3D.scissor_mat(load(fp))
		var tf: Array[Transform3D] = []
		var tries := 0
		while tf.size() < 80 and tries < 900:
			tries += 1
			var x := rng.randf_range(Config.WORLD.position.x + 2, Config.WORLD.end.x - 2)
			var z := rng.randf_range(Config.WORLD.position.y + 2, Config.WORLD.end.y - 2)
			if _in_skip(x, z):
				continue
			var b := Basis().rotated(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.8, 1.2))
			tf.append(Transform3D(b, Vector3(x, Config.ground_y(Vector2(x, z)), z)))
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = src
		mm.instance_count = tf.size()
		for i in tf.size():
			mm.set_instance_transform(i, tf[i])
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		mmi.material_override = mat
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mmi)


func _build_rocks() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 99
	var sm := SphereMesh.new()
	sm.radius = 0.45; sm.height = 0.7; sm.radial_segments = 6; sm.rings = 3
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.55, 0.55, 0.58); mat.roughness = 1.0
	var tf: Array[Transform3D] = []
	var tries := 0
	while tf.size() < 36 and tries < 400:
		tries += 1
		var x := rng.randf_range(Config.WORLD.position.x + 3, Config.WORLD.end.x - 3)
		var z := rng.randf_range(Config.WORLD.position.y + 3, Config.WORLD.end.y - 3)
		if _in_skip(x, z):
			continue
		var s := rng.randf_range(0.6, 1.4)
		var b := Basis().rotated(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * 0.8, s))
		tf.append(Transform3D(b, Vector3(x, Config.ground_y(Vector2(x, z)) + 0.15 * s, z)))
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = sm
	mm.instance_count = tf.size()
	for i in tf.size():
		mm.set_instance_transform(i, tf[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mmi)


func _build_fences() -> void:
	var seg := _fence_seg()
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.5, 0.36, 0.24); mat.roughness = 1.0
	var pts: Array[Vector2] = []
	var x := -40.0
	while x <= -16.0:
		pts.append(Vector2(x, 14.0)); x += 1.6
	var z := -14.0
	while z <= 14.0:
		pts.append(Vector2(-40.0, z)); z += 1.6
	var tf: Array[Transform3D] = []
	for p in pts:
		tf.append(Transform3D(Basis(), Vector3(p.x, Config.ground_y(p), p.y)))
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = seg
	mm.instance_count = tf.size()
	for i in tf.size():
		mm.set_instance_transform(i, tf[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mmi)


func _fence_seg() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	SpriteLib3D.box_into(st, Vector3(0, 0.45, 0), Vector3(0.14, 0.9, 0.14))
	SpriteLib3D.box_into(st, Vector3(0.8, 0.6, 0), Vector3(1.6, 0.12, 0.06))
	SpriteLib3D.box_into(st, Vector3(0.8, 0.32, 0), Vector3(1.6, 0.12, 0.06))
	st.generate_normals()
	return st.commit()


func _build_props() -> void:
	# 房子（3D box，投真实阴影）：农场农舍 / 酒馆
	_box(Vector2(-30, -11), 3.2, Vector3(5, 3.2, 4.5), Color(0.82, 0.5, 0.34))
	_box(Vector2(30, 10), 2.6, Vector3(4.2, 2.6, 3.6), Color(0.72, 0.45, 0.4))
	_box(Vector2(6, -10), 2.2, Vector3(3.2, 2.2, 3), Color(0.7, 0.6, 0.5))    # 广场杂货铺
	# 林缘 billboard 树
	var rng := RandomNumberGenerator.new()
	rng.seed = 4242
	for p in [Vector2(-41, -15), Vector2(-38, 15), Vector2(41, -14), Vector2(38, 16),
			Vector2(-20, -15), Vector2(20, 15), Vector2(0, -16), Vector2(12, 16),
			Vector2(-12, 15), Vector2(42, 2), Vector2(-42, 4)]:
		_tree(p + Vector2(rng.randf_range(-1, 1), rng.randf_range(-1, 1)))


func _box(pos: Vector2, h: float, size: Vector3, col: Color) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.position = Vector3(pos.x, Config.ground_y(pos) + h / 2.0, pos.y)
	var m := StandardMaterial3D.new()
	m.albedo_color = col; m.roughness = 1.0
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mi)


func _tree(pos: Vector2) -> void:
	var holder := Node3D.new()
	holder.position = Vector3(pos.x, Config.ground_y(pos), pos.y)
	holder.add_child(SpriteLib3D.make_blob(load(Config.T_BLOB), 1.0))
	var s := Sprite3D.new()
	s.texture = load(Config.T_TREE)
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.pixel_size = Config.TREE_PX
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = false
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	s.position.y = 32 * Config.TREE_PX / 2.0
	holder.add_child(s)
	add_child(holder)


# ---- 昼夜（简化：按世界时间调方向光颜色/强度）----------------------------

func _apply_daynight(hhmm: String) -> void:
	var parts := hhmm.split(":")
	if parts.size() != 2 or _sun == null:
		return
	var m := int(parts[0]) * 60 + int(parts[1])
	var night := 0.0    # 0 白天 1 深夜
	if m >= 18 * 60 and m < 20 * 60:
		night = (m - 18 * 60) / 120.0
	elif m >= 20 * 60 or m < 5 * 60:
		night = 1.0
	elif m >= 5 * 60 and m < 7 * 60:
		night = 1.0 - (m - 5 * 60) / 120.0
	_sun.light_energy = lerpf(1.1, 0.18, night)
	_sun.light_color = Color(1.0, 0.96, 0.86).lerp(Color(0.55, 0.6, 0.85), night)


# ---- HUD / BGM -----------------------------------------------------------

func _build_hud() -> void:
	var ui := CanvasLayer.new()
	add_child(ui)
	_clock = _mk_label(Vector2(16, 12), 22, Color(1, 1, 1))
	ui.add_child(_clock)
	_event = _mk_label(Vector2(16, 44), 16, Color(0.85, 0.95, 0.75))
	_event.visible = false
	ui.add_child(_event)
	_banner = _mk_label(Vector2(16, 72), 16, Color(1, 0.6, 0.55))
	_banner.visible = false
	ui.add_child(_banner)
	_hint = _mk_label(Vector2(16, 688), 15, Color(1, 1, 1, 0.8))
	_hint.text = "WASD/方向键 走动 · 走进区域即可前往 · Tab 打开小镇通"
	ui.add_child(_hint)


func _mk_label(pos: Vector2, size: int, col: Color) -> Label:
	var l := Label.new()
	l.position = pos
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	l.add_theme_constant_override("shadow_offset_y", 2)
	return l


func _build_bgm() -> void:
	var bgm := AudioStreamPlayer.new()
	var stream := load("res://assets/audio/theme_village.ogg")
	if stream is AudioStreamOggVorbis:
		(stream as AudioStreamOggVorbis).loop = true
	if stream != null:
		bgm.stream = stream
		bgm.volume_db = -14.0
		bgm.autoplay = true
		add_child(bgm)
		bgm.play()
