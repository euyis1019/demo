extends Node3D
## 全 3D 静态场景（伪 3D：地形/草/花/石/栅/菜畦全部立体构建，角色保持 billboard 立绘）。
## 依据《全 3D 场景调研》落地，铁律：web Compatibility(WebGL2) 单线程可用特性、全代码生成、
## 复用现有像素纹理。核心：
##  * height(x,z) 单一真相源 → 地面网格 + 一切贴地物 y 全喂它，杜绝浮空/陷地。
##  * 地形：SurfaceTool 起伏 ArrayMesh + 顶点色 splat shader 混草/泥（单 draw call）。
##  * 草/花：交叉双 quad 源 mesh + 分块 MultiMeshInstance3D + ALPHA_SCISSOR（绝不 blend）+ 风 shader。
##  * 石/栅/菜畦：程序化网格（MultiMesh 合批），唯它们投真实方向光阴影；草/角色关投影 + blob 假影。

const GRASS := "res://assets/grass.png"
const DIRT := "res://assets/dirt.png"
const TREE := "res://assets/tree.png"
const BLOB := "res://assets/blob.png"
const BLADE := "res://assets/blade.png"
const TUFT := "res://assets/grasstuft2.png"
const FLOWERS := ["res://assets/flower_red.png", "res://assets/flower_yellow.png",
	"res://assets/flower_white.png", "res://assets/flower_purple.png"]
const CHARS := ["res://assets/char_5.png", "res://assets/char_9.png", "res://assets/char_2.png"]
const ROW_OF := {"down": 0, "right": 1, "up": 2, "left": 3}

const SPEED := 6.0
const CHAR_PX := 0.09
const TREE_PX := 0.09
const WORLD := 80.0            # 地图边长（-40..40）
const PLAZA_R := 6.5           # 中央夯土广场半径

var _noise := FastNoiseLite.new()
var _rng := RandomNumberGenerator.new()
var _player: Node3D
var _player_spr: AnimatedSprite3D
var _cam: Camera3D
var _facing := "down"
var _hud: Label

# 菜畦矩形（farm 区，跳过草/计算地面材质用）
var _beds: Array[Rect2] = []


func _ready() -> void:
	_rng.seed = 20260616
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_noise.frequency = 0.03
	_noise.seed = 12345
	_define_beds()
	_build_env()
	_build_terrain()
	_build_beds()
	_build_grass_chunks()
	_build_flowers()
	_build_rocks()
	_build_fences()
	_build_props()
	_build_npcs()
	_player = _make_char(CHARS[0], Vector2(0, 4))
	_player_spr = _player.get_node("spr")
	add_child(_player)
	_cam = Camera3D.new()
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	_cam.size = 14.0
	add_child(_cam)
	_update_cam()
	_build_hud()


func _process(delta: float) -> void:
	var ix := (1.0 if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT) else 0.0) \
		- (1.0 if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT) else 0.0)
	var iz := (1.0 if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN) else 0.0) \
		- (1.0 if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP) else 0.0)
	var dir := Vector3(ix, 0, iz)
	if dir.length() > 0.01:
		dir = dir.normalized()
		var np := _player.position + dir * SPEED * delta
		np.y = ground_y(Vector2(np.x, np.z))   # 贴地
		_player.position = np
		_facing = _dir_name(ix, iz)
		_player_spr.play("walk_%s" % _facing)
	else:
		_player_spr.play("idle_%s" % _facing)
	_update_cam()
	if _hud != null:
		var dc := Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
		var prim := Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
		_hud.text = "FPS %d  draw_calls %d  tris %d" % [
			Engine.get_frames_per_second(), int(dc), int(prim)]


# ---- 地形高度：单一真相源 ------------------------------------------------

func height(x: float, z: float) -> float:
	return _noise.get_noise_2d(x, z) * 0.6   # ±0.6 缓坡


func ground_y(p: Vector2) -> float:
	return height(p.x, p.y)


# ---- 相机 / 朝向 ----------------------------------------------------------

func _update_cam() -> void:
	_cam.position = _player.position + Vector3(0, 16, 13)
	_cam.look_at(_player.position + Vector3(0, 0.5, 0), Vector3.UP)


func _dir_name(ix: float, iz: float) -> String:
	if absf(ix) > absf(iz):
		return "right" if ix > 0 else "left"
	return "down" if iz > 0 else "up"


# ---- 环境与光照 ----------------------------------------------------------

func _build_env() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_horizon_color = Color(0.75, 0.85, 0.95)
	sm.sky_top_color = Color(0.45, 0.7, 1.0)
	sm.ground_horizon_color = Color(0.6, 0.7, 0.55)
	sky.sky_material = sm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.6
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -50, 0)
	sun.light_energy = 1.1
	sun.light_color = Color(1.0, 0.96, 0.86)
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 36.0   # 收紧分摊更高有效阴影分辨率
	add_child(sun)


# ---- 地形：SurfaceTool 起伏网格 + 顶点色 splat -----------------------------

func _build_terrain() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n := int(WORLD)              # 80x80 格（1 单位/格）
	var half := WORLD / 2.0
	for cz in range(n):
		for cx in range(n):
			var x0 := cx - half
			var z0 := cz - half
			var x1 := x0 + 1.0
			var z1 := z0 + 1.0
			_terr_vert(st, x0, z0); _terr_vert(st, x1, z0); _terr_vert(st, x1, z1)
			_terr_vert(st, x0, z0); _terr_vert(st, x1, z1); _terr_vert(st, x0, z1)
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _terrain_mat()
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


func _terr_vert(st: SurfaceTool, x: float, z: float) -> void:
	st.set_color(_splat_color(x, z))     # 必须在 add_vertex 之前
	st.set_uv(Vector2(x, z))
	st.add_vertex(Vector3(x, height(x, z), z))


## 顶点色 splat：R=草权重 G=泥权重；广场圆盘+菜畦为泥，平滑过渡
func _splat_color(x: float, z: float) -> Color:
	var d := smoothstep(PLAZA_R + 2.0, PLAZA_R - 1.0, Vector2(x, z).length())  # 广场
	for b in _beds:
		if b.grow(0.6).has_point(Vector2(x, z)):
			d = max(d, 0.85)
	return Color(1.0 - d, d, 0.0)


func _terrain_mat() -> ShaderMaterial:
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode cull_back;
uniform sampler2D grass_tex : source_color, filter_nearest, repeat_enable;
uniform sampler2D dirt_tex : source_color, filter_nearest, repeat_enable;
uniform float tex_scale = 0.5;
void fragment() {
	vec2 uv = UV * tex_scale;
	vec3 g = texture(grass_tex, uv).rgb;
	vec3 d = texture(dirt_tex, uv).rgb;
	float gw = COLOR.r;
	float dw = COLOR.g;
	ALBEDO = (g * gw + d * dw) / max(gw + dw, 0.001);
}
"""
	var m := ShaderMaterial.new()
	m.shader = sh
	m.set_shader_parameter("grass_tex", load(GRASS))
	m.set_shader_parameter("dirt_tex", load(DIRT))
	m.set_shader_parameter("tex_scale", 0.5)
	return m


# ---- 区域判定（散点时跳过非草区）-----------------------------------------

func _define_beds() -> void:
	# farm 区（左侧）几排菜畦
	for row in 3:
		_beds.append(Rect2(-22.0, -6.0 + row * 5.0, 11.0, 2.6))


func _in_plaza(x: float, z: float) -> bool:
	return Vector2(x, z).length() < PLAZA_R + 0.5


func _in_beds(x: float, z: float) -> bool:
	for b in _beds:
		if b.has_point(Vector2(x, z)):
			return true
	return false


# ---- 草：交叉双 quad 源 mesh + 分块 MultiMesh + 风 shader -------------------

func _build_grass_chunks() -> void:
	var src := _cross_quad(0.6, 0.95, Vector2(0, 1), Vector2(1, 0))    # 高草叶
	var mat := _wind_grass_mat(BLADE)
	var src_tuft := _cross_quad(0.85, 0.85, Vector2(0, 1), Vector2(1, 0))  # 蓬松草丛（主）
	var mat_tuft := _wind_grass_mat(TUFT)
	var chunk := 10.0
	var half := WORLD / 2.0
	for cz in int(WORLD / chunk):
		for cx in int(WORLD / chunk):
			var ox := -half + cx * chunk
			var oz := -half + cz * chunk
			_grass_chunk(src_tuft, mat_tuft, ox, oz, chunk, 55, 0.0)   # 主：蓬松草丛铺满
			_grass_chunk(src, mat, ox, oz, chunk, 35, 0.0)             # 辅：高草叶点缀


func _grass_chunk(src: ArrayMesh, mat: Material, ox: float, oz: float,
		size: float, count: int, scale_base: float) -> void:
	var tf: Array[Transform3D] = []
	for _i in count:
		var x := ox + _rng.randf() * size
		var z := oz + _rng.randf() * size
		if _in_plaza(x, z) or _in_beds(x, z):
			continue
		var s := _rng.randf_range(0.7, 1.3)
		var b := Basis().rotated(Vector3.UP, _rng.randf() * TAU).scaled(Vector3.ONE * s)
		tf.append(Transform3D(b, Vector3(x, ground_y(Vector2(x, z)), z)))
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


# ---- 花：交叉双 quad + 静态 scissor 材质（花基本不摆）---------------------

func _build_flowers() -> void:
	for fi in FLOWERS.size():
		var src := _cross_quad(0.5, 0.7, Vector2(0, 1), Vector2(1, 0))
		var mat := _scissor_mat(FLOWERS[fi])
		var tf: Array[Transform3D] = []
		var tries := 0
		while tf.size() < 90 and tries < 800:
			tries += 1
			var x := _rng.randf_range(-38, 38)
			var z := _rng.randf_range(-38, 38)
			if _in_plaza(x, z) or _in_beds(x, z):
				continue
			var b := Basis().rotated(Vector3.UP, _rng.randf() * TAU) \
				.scaled(Vector3.ONE * _rng.randf_range(0.8, 1.2))
			tf.append(Transform3D(b, Vector3(x, ground_y(Vector2(x, z)), z)))
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


# ---- 石头：低面 SphereMesh + MultiMesh（投真实阴影）-----------------------

func _build_rocks() -> void:
	var sm := SphereMesh.new()
	sm.radius = 0.45
	sm.height = 0.7
	sm.radial_segments = 6
	sm.rings = 3
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.55, 0.55, 0.58)
	mat.roughness = 1.0
	var tf: Array[Transform3D] = []
	var tries := 0
	while tf.size() < 40 and tries < 400:
		tries += 1
		var x := _rng.randf_range(-38, 38)
		var z := _rng.randf_range(-38, 38)
		if _in_plaza(x, z) or _in_beds(x, z):
			continue
		var s := _rng.randf_range(0.6, 1.5)
		var b := Basis().rotated(Vector3.UP, _rng.randf() * TAU).scaled(
			Vector3(s, s * _rng.randf_range(0.6, 0.9), s))
		tf.append(Transform3D(b, Vector3(x, ground_y(Vector2(x, z)) + 0.15 * s, z)))
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


# ---- 栅栏：程序化「柱+横档」段 MultiMesh，沿 farm 边界（投阴影）-----------

func _build_fences() -> void:
	var seg := _fence_segment_mesh()
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.5, 0.36, 0.24)
	mat.roughness = 1.0
	var pts: Array[Vector2] = []
	# farm 区一道 L 形篱笆
	var x := -28.0
	while x <= -8.0:
		pts.append(Vector2(x, 13.0)); x += 1.6
	var z := -13.0
	while z <= 13.0:
		pts.append(Vector2(-28.0, z)); z += 1.6
	var tf: Array[Transform3D] = []
	for p in pts:
		tf.append(Transform3D(Basis(), Vector3(p.x, ground_y(p) , p.y)))
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


func _fence_segment_mesh() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_box_into(st, Vector3(0, 0.45, 0), Vector3(0.14, 0.9, 0.14))      # 柱
	_box_into(st, Vector3(0.8, 0.6, 0), Vector3(1.6, 0.12, 0.06))     # 上横档
	_box_into(st, Vector3(0.8, 0.32, 0), Vector3(1.6, 0.12, 0.06))    # 下横档
	st.generate_normals()
	return st.commit()


# ---- 菜畦：矮 BoxMesh 阵列（dirt 纹理，投阴影）----------------------------

func _build_beds() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = load(DIRT)
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	mat.uv1_scale = Vector3(4, 2, 1)
	for b in _beds:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(b.size.x, 0.22, b.size.y)
		mi.mesh = bm
		var c := b.get_center()
		mi.position = Vector3(c.x, ground_y(c) + 0.02, c.y)
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		add_child(mi)


# ---- 房子 + billboard 树 --------------------------------------------------

func _build_props() -> void:
	_box(Vector2(-15, -10), 3.4, Vector3(4.5, 3.2, 4), Color(0.82, 0.5, 0.34))   # farm 农舍
	_box(Vector2(15, 9), 2.4, Vector3(3.4, 2.4, 3), Color(0.72, 0.5, 0.42))      # tavern
	# 林缘 billboard 树
	for p in [Vector2(-34, -30), Vector2(-30, 30), Vector2(33, -28), Vector2(30, 32),
			Vector2(-36, 6), Vector2(36, -6), Vector2(8, -34), Vector2(-6, 35),
			Vector2(22, 22), Vector2(-22, -24)]:
		_tree(p)


func _box(pos: Vector2, h: float, size: Vector3, col: Color) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.position = Vector3(pos.x, ground_y(pos) + h / 2.0, pos.y)
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = 1.0
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mi)


func _tree(pos: Vector2) -> void:
	var holder := Node3D.new()
	holder.position = Vector3(pos.x, ground_y(pos), pos.y)
	holder.add_child(_make_blob(1.0))
	var s := Sprite3D.new()
	s.texture = load(TREE)
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.pixel_size = TREE_PX
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.shaded = false
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	s.position.y = 32 * TREE_PX / 2.0
	holder.add_child(s)
	add_child(holder)


# ---- 角色：AnimatedSprite3D billboard 立绘（贴地）------------------------

func _build_npcs() -> void:
	add_child(_make_char(CHARS[1], Vector2(-3, -1)))   # 老钱
	add_child(_make_char(CHARS[2], Vector2(4, 1)))     # 大山


func _make_char(path: String, pos: Vector2) -> Node3D:
	var holder := Node3D.new()
	holder.position = Vector3(pos.x, ground_y(pos), pos.y)
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
	spr.position.y = 16 * CHAR_PX / 2.0
	spr.play("idle_down")
	holder.add_child(spr)
	return holder


func _make_blob(radius: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(radius * 2.0, radius * 2.0)
	mi.mesh = q
	mi.rotation_degrees = Vector3(-90, 0, 0)
	mi.position.y = 0.04
	var m := StandardMaterial3D.new()
	m.albedo_texture = load(BLOB)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


# ---- 通用：交叉双 quad 源 mesh / 盒子 / 材质 / 帧 ------------------------

## 两片 90° 相交的 quad（草根在 y=0、草尖在 y=h）；uv 底=1 顶=0（配风 mask）
func _cross_quad(w: float, h: float, uv_bottom: Vector2, uv_top: Vector2) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var hw := w / 2.0
	_quad_into(st, Vector3(-hw, 0, 0), Vector3(hw, 0, 0), Vector3(hw, h, 0), Vector3(-hw, h, 0))
	_quad_into(st, Vector3(0, 0, -hw), Vector3(0, 0, hw), Vector3(0, h, hw), Vector3(0, h, -hw))
	return st.commit()


func _quad_into(st: SurfaceTool, bl: Vector3, br: Vector3, tr: Vector3, tl: Vector3) -> void:
	st.set_normal(Vector3.UP)
	st.set_uv(Vector2(0, 1)); st.add_vertex(bl)
	st.set_uv(Vector2(1, 1)); st.add_vertex(br)
	st.set_uv(Vector2(1, 0)); st.add_vertex(tr)
	st.set_uv(Vector2(0, 1)); st.add_vertex(bl)
	st.set_uv(Vector2(1, 0)); st.add_vertex(tr)
	st.set_uv(Vector2(0, 0)); st.add_vertex(tl)


func _box_into(st: SurfaceTool, center: Vector3, size: Vector3) -> void:
	var h := size * 0.5
	var v := [
		center + Vector3(-h.x, -h.y, -h.z), center + Vector3(h.x, -h.y, -h.z),
		center + Vector3(h.x, -h.y, h.z), center + Vector3(-h.x, -h.y, h.z),
		center + Vector3(-h.x, h.y, -h.z), center + Vector3(h.x, h.y, -h.z),
		center + Vector3(h.x, h.y, h.z), center + Vector3(-h.x, h.y, h.z),
	]
	var faces := [[0,1,2,3], [7,6,5,4], [4,5,1,0], [6,7,3,2], [5,6,2,1], [7,4,0,3]]
	for f in faces:
		st.add_vertex(v[f[0]]); st.add_vertex(v[f[1]]); st.add_vertex(v[f[2]])
		st.add_vertex(v[f[0]]); st.add_vertex(v[f[2]]); st.add_vertex(v[f[3]])


func _scissor_mat(tex_path: String) -> BaseMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = load(tex_path)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	m.alpha_scissor_threshold = 0.5
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return m


## 草风材质：cull_disabled+unshaded，顶点位移（世界相位+TIME+UV.y mask），discard 抠图
func _wind_grass_mat(tex_path: String) -> ShaderMaterial:
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode cull_disabled, unshaded;
uniform sampler2D tex : source_color, filter_nearest;
uniform sampler2D wind_noise : repeat_enable;
uniform vec2 wind_direction = vec2(1.0, 0.3);
uniform float wind_strength = 0.18;
void vertex() {
	vec2 wp = NODE_POSITION_WORLD.xz / 10.0;
	wp -= TIME * wind_direction * wind_strength;
	float bend = texture(wind_noise, wp).x - 0.5;
	float mask = 1.0 - UV.y;
	VERTEX.x += bend * mask * wind_strength * 3.0;
	VERTEX.z += bend * mask * wind_strength * 1.5;
}
void fragment() {
	vec4 c = texture(tex, UV);
	if (c.a < 0.5) { discard; }
	ALBEDO = c.rgb;
}
"""
	var nt := NoiseTexture2D.new()
	nt.seamless = true
	var n := FastNoiseLite.new()
	n.frequency = 0.05
	nt.noise = n
	var m := ShaderMaterial.new()
	m.shader = sh
	m.set_shader_parameter("tex", load(tex_path))
	m.set_shader_parameter("wind_noise", nt)
	return m


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


# ---- 性能 HUD（Step 0：先有标尺再加量）----------------------------------

func _build_hud() -> void:
	var cl := CanvasLayer.new()
	add_child(cl)
	_hud = Label.new()
	_hud.position = Vector2(12, 10)
	_hud.add_theme_font_size_override("font_size", 18)
	_hud.add_theme_color_override("font_color", Color(1, 1, 0.5))
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	cl.add_child(_hud)
