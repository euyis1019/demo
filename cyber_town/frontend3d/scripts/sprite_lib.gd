class_name SpriteLib3D
## 3D 表现层共用工厂：4 向 SpriteFrames / 交叉双 quad / 各材质（地形 splat、草风、
## alpha scissor、blob 接地影）/ billboard 角色精灵。全程序化，复用现有像素纹理。

const ROW_OF := {"down": 0, "right": 1, "up": 2, "left": 3}
const WALK_FPS := 7.0


# ---- 角色帧（16×16，4 列走帧 × 行：下/右/上/左）----

static func build_frames(tex: Texture2D) -> SpriteFrames:
	var f := SpriteFrames.new()
	f.remove_animation("default")
	for dir in ROW_OF:
		var row: int = ROW_OF[dir]
		var walk := "walk_%s" % dir
		f.add_animation(walk); f.set_animation_speed(walk, WALK_FPS); f.set_animation_loop(walk, true)
		for col in 4:
			f.add_frame(walk, _cut(tex, col, row))
		var idle := "idle_%s" % dir
		f.add_animation(idle); f.set_animation_speed(idle, 1.0); f.set_animation_loop(idle, true)
		f.add_frame(idle, _cut(tex, 0, row))
	return f


static func _cut(tex: Texture2D, col: int, row: int) -> AtlasTexture:
	var at := AtlasTexture.new()
	at.atlas = tex
	at.region = Rect2(col * 16, row * 16, 16, 16)
	return at


static func dir_name(v: Vector2, fallback := "down") -> String:
	if v.length_squared() < 0.0001:
		return fallback
	if absf(v.x) > absf(v.y):
		return "right" if v.x > 0 else "left"
	return "down" if v.y > 0 else "up"


## billboard 角色：AnimatedSprite3D（FIXED_Y / scissor / nearest / 脚底贴地）
static func make_char_sprite(tex: Texture2D, px: float) -> AnimatedSprite3D:
	var spr := AnimatedSprite3D.new()
	spr.sprite_frames = build_frames(tex)
	spr.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	spr.pixel_size = px
	spr.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	spr.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	spr.shaded = false
	spr.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	spr.position.y = 16 * px / 2.0
	spr.play("idle_down")
	return spr


# ---- 交叉双 quad（草/花源 mesh）----

static func cross_quad(w: float, h: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var hw := w / 2.0
	_quad(st, Vector3(-hw, 0, 0), Vector3(hw, 0, 0), Vector3(hw, h, 0), Vector3(-hw, h, 0))
	_quad(st, Vector3(0, 0, -hw), Vector3(0, 0, hw), Vector3(0, h, hw), Vector3(0, h, -hw))
	return st.commit()


static func _quad(st: SurfaceTool, bl: Vector3, br: Vector3, tr: Vector3, tl: Vector3) -> void:
	st.set_normal(Vector3.UP)
	st.set_uv(Vector2(0, 1)); st.add_vertex(bl)
	st.set_uv(Vector2(1, 1)); st.add_vertex(br)
	st.set_uv(Vector2(1, 0)); st.add_vertex(tr)
	st.set_uv(Vector2(0, 1)); st.add_vertex(bl)
	st.set_uv(Vector2(1, 0)); st.add_vertex(tr)
	st.set_uv(Vector2(0, 0)); st.add_vertex(tl)


static func box_into(st: SurfaceTool, center: Vector3, size: Vector3) -> void:
	var h := size * 0.5
	var v := [
		center + Vector3(-h.x, -h.y, -h.z), center + Vector3(h.x, -h.y, -h.z),
		center + Vector3(h.x, -h.y, h.z), center + Vector3(-h.x, -h.y, h.z),
		center + Vector3(-h.x, h.y, -h.z), center + Vector3(h.x, h.y, -h.z),
		center + Vector3(h.x, h.y, h.z), center + Vector3(-h.x, h.y, h.z),
	]
	var faces := [[0,1,2,3], [7,6,5,4], [4,5,1,0], [6,7,3,2], [5,6,2,1], [7,4,0,3]]
	for fc in faces:
		st.add_vertex(v[fc[0]]); st.add_vertex(v[fc[1]]); st.add_vertex(v[fc[2]])
		st.add_vertex(v[fc[0]]); st.add_vertex(v[fc[2]]); st.add_vertex(v[fc[3]])


# ---- 材质 ----

static func terrain_mat(grass: Texture2D, dirt: Texture2D) -> ShaderMaterial:
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
	float gw = COLOR.r; float dw = COLOR.g;
	ALBEDO = (g * gw + d * dw) / max(gw + dw, 0.001);
}
"""
	var m := ShaderMaterial.new()
	m.shader = sh
	m.set_shader_parameter("grass_tex", grass)
	m.set_shader_parameter("dirt_tex", dirt)
	m.set_shader_parameter("tex_scale", 0.5)
	return m


static func grass_wind_mat(tex: Texture2D) -> ShaderMaterial:
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
	m.set_shader_parameter("tex", tex)
	m.set_shader_parameter("wind_noise", nt)
	return m


static func scissor_mat(tex: Texture2D) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	m.alpha_scissor_threshold = 0.5
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return m


static func make_blob(tex: Texture2D, radius: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(radius * 2.0, radius * 2.0)
	mi.mesh = q
	mi.rotation_degrees = Vector3(-90, 0, 0)
	mi.position.y = 0.04
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


const _FONT_PATH := "res://assets/fonts/fusion-pixel-zh.ttf"
static var _font: Font = null

## 头顶 Label3D（名牌/状态/气泡用）：billboard、描边、中文像素字、恒在最上层
static func make_label(size := 64, color := Color.WHITE) -> Label3D:
	var l := Label3D.new()
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true                # 不被草/物件遮挡
	l.pixel_size = 0.006                  # 世界尺寸 = font_size * pixel_size
	l.font_size = size
	if _font == null and ResourceLoader.exists(_FONT_PATH):
		_font = load(_FONT_PATH)
	if _font != null:
		l.font = _font                    # 显式中文字体（默认字体无中文字形）
	l.outline_size = max(6, int(size / 5))
	l.modulate = color
	l.outline_modulate = Color(0, 0, 0, 0.95)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.render_priority = 4
	l.outline_render_priority = 3
	l.alpha_cut = Label3D.ALPHA_CUT_DISCARD
	return l
