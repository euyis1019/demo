extends Node3D
## 2.5D 伪 3D Spike：正交 Camera3D 俯视 + 纹理 3D 地面 + DirectionalLight3D 真实
## 光影 + 现有 Ninja Adventure 像素角色用 AnimatedSprite3D(billboard FIXED_Y) 做立绘。
## 验证「2D 立绘站在 3D 地面上、随相机朝向、有阴影与深度」的观感。
## 独立工程、不连后端，WASD/方向键走动（坐标 Vector3，对应后端 Vector2→(x,0,y)）。

const GRASS := "res://assets/grass.png"
const DIRT := "res://assets/dirt.png"
const TREE := "res://assets/tree.png"
const BLOB := "res://assets/blob.png"
const CHARS := ["res://assets/char_5.png", "res://assets/char_9.png", "res://assets/char_2.png"]
const ROW_OF := {"down": 0, "right": 1, "up": 2, "left": 3}

const SPEED := 6.0
const CHAR_PX := 0.09          # AnimatedSprite3D.pixel_size（16px 角色 ≈ 1.44 单位高）
const TREE_PX := 0.09          # 32px 绿丛 ≈ 2.9 单位（约 2 倍角色高）

var _player: Node3D
var _player_spr: AnimatedSprite3D
var _cam: Camera3D
var _facing := "down"


func _ready() -> void:
	_build_env()
	_build_ground()
	_build_plaza()
	_build_props()
	_build_npcs()
	_player = _make_char(CHARS[0], Vector3(0, 0, 2))
	_player_spr = _player.get_node("spr")
	add_child(_player)
	_cam = Camera3D.new()
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	_cam.size = 14.0
	add_child(_cam)
	_update_cam()


func _process(delta: float) -> void:
	var ix := (1.0 if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT) else 0.0) \
		- (1.0 if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT) else 0.0)
	var iz := (1.0 if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN) else 0.0) \
		- (1.0 if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP) else 0.0)
	var dir := Vector3(ix, 0, iz)
	if dir.length() > 0.01:
		dir = dir.normalized()
		_player.position += dir * SPEED * delta
		_facing = _dir_name(ix, iz)
		_player_spr.play("walk_%s" % _facing)
	else:
		_player_spr.play("idle_%s" % _facing)
	_update_cam()


func _update_cam() -> void:
	# 相机定在玩家斜上方、看向玩家 → 固定 ~51° 俯角的正交斜视
	_cam.position = _player.position + Vector3(0, 16, 13)
	_cam.look_at(_player.position + Vector3(0, 0.5, 0), Vector3.UP)


func _dir_name(ix: float, iz: float) -> String:
	if absf(ix) > absf(iz):
		return "right" if ix > 0 else "left"
	return "down" if iz > 0 else "up"   # +Z 朝相机（屏幕下方）


# ---- 环境与光照 ----

func _build_env() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_horizon_color = Color(0.75, 0.85, 0.95)
	sm.sky_top_color = Color(0.45, 0.7, 1.0)
	sky.sky_material = sm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.55
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -50, 0)
	sun.light_energy = 1.1
	sun.light_color = Color(1.0, 0.96, 0.86)
	sun.shadow_enabled = true
	add_child(sun)


# ---- 地面（3D 网格 + 平铺纹理）----

func _build_ground() -> void:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(80, 80)
	mi.mesh = pm
	mi.material_override = _ground_mat(GRASS, 40.0)
	add_child(mi)


func _build_plaza() -> void:
	# 一片夯土广场（略抬 0.01 防 z-fighting），展示地面材质分区
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(14, 14)
	mi.mesh = pm
	mi.position = Vector3(0, 0.01, 0)
	mi.material_override = _ground_mat(DIRT, 7.0)
	add_child(mi)


func _ground_mat(tex_path: String, tiling: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = load(tex_path)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.uv1_scale = Vector3(tiling, tiling, 1)
	return m


# ---- 道具：3D 房子（真实几何+阴影）+ billboard 树（Don't Starve 式）----

func _build_props() -> void:
	_box(Vector3(-7, 1.6, -7), Vector3(4.5, 3.2, 4), Color(0.82, 0.5, 0.34))   # 茅草色房子
	_box(Vector3(8, 1.1, 6), Vector3(3, 2.2, 3), Color(0.7, 0.62, 0.5))        # 小屋
	for p in [Vector3(5, 0, -6), Vector3(-9, 0, 4), Vector3(10, 0, -3),
			Vector3(-4, 0, 9), Vector3(3, 0, 10), Vector3(-11, 0, -3)]:
		_tree(p)


func _box(pos: Vector3, size: Vector3, col: Color) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.position = pos
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mi)


func _tree(pos: Vector3) -> void:
	var holder := Node3D.new()
	holder.position = pos
	holder.add_child(_make_blob(1.0))
	var s := Sprite3D.new()
	s.texture = load(TREE)
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.pixel_size = TREE_PX
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = false
	# 关精灵自投影：扁平 billboard 投影很难看，地面用柔和 blob 影代替
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	s.position.y = 32 * TREE_PX / 2.0   # tree.png 为 32×32 圆绿丛
	holder.add_child(s)
	add_child(holder)


# ---- 角色：AnimatedSprite3D billboard 立绘（复用现有像素帧）----

func _build_npcs() -> void:
	add_child(_make_char(CHARS[1], Vector3(-3, 0, -2)))   # 老钱
	add_child(_make_char(CHARS[2], Vector3(4, 0, 1)))     # 大山


func _make_char(path: String, pos: Vector3) -> Node3D:
	var holder := Node3D.new()
	holder.position = pos
	holder.add_child(_make_blob(0.55))
	var spr := AnimatedSprite3D.new()
	spr.name = "spr"
	spr.sprite_frames = _build_frames(load(path))
	spr.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	spr.pixel_size = CHAR_PX
	spr.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	spr.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	spr.shaded = false
	spr.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	spr.position.y = 16 * CHAR_PX / 2.0   # 脚底落在地面
	spr.play("idle_down")
	holder.add_child(spr)
	return holder


func _make_blob(radius: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(radius * 2.0, radius * 2.0)
	mi.mesh = q
	mi.rotation_degrees = Vector3(-90, 0, 0)   # 平铺到地面
	mi.position.y = 0.02
	var m := StandardMaterial3D.new()
	m.albedo_texture = load(BLOB)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


func _build_frames(tex: Texture2D) -> SpriteFrames:
	var f := SpriteFrames.new()
	f.remove_animation("default")
	for dir in ROW_OF:
		var row: int = ROW_OF[dir]
		var walk := "walk_%s" % dir
		f.add_animation(walk)
		f.set_animation_speed(walk, 7.0)
		f.set_animation_loop(walk, true)
		for col in 4:
			f.add_frame(walk, _cut(tex, col, row))
		var idle := "idle_%s" % dir
		f.add_animation(idle)
		f.set_animation_speed(idle, 1.0)
		f.set_animation_loop(idle, true)
		f.add_frame(idle, _cut(tex, 0, row))
	return f


func _cut(tex: Texture2D, col: int, row: int) -> AtlasTexture:
	var at := AtlasTexture.new()
	at.atlas = tex
	at.region = Rect2(col * 16, row * 16, 16, 16)
	return at
