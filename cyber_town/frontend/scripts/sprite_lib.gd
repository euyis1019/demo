class_name SpriteLib
## 精灵帧工具 + 共享视觉件工厂（W7 画面升级）。
##
## 当前素材（Ninja Adventure，CC0）：16×16/帧（64×112 = 4 列走帧 × 7 行，
## 前 4 行为行走方向）。行序（截图迭代核实）：行0=下 / 行1=右 / 行2=上 / 行3=左。
##
## W7 新增（全部程序化生成，零新素材；纹理用 static 缓存全场共享）：
## make_shadow 脚下软阴影 / make_panel_style UI 深色 pill /
## make_particle_tex CPU 粒子白点（web Compatibility 必须显式给 texture，
## 已知坑 godot#96030）/ make_radial_tex 径向渐变（灯光/阴影共用）/
## pop_bubble & fade_bubble 气泡 Q 弹出现与淡出演出。

const FRAME_W := 16
const FRAME_H := 16
const WALK_FPS := 7.0

const ROW_OF := {"down": 0, "right": 1, "up": 2, "left": 3}

static var _shadow_tex: Texture2D = null
static var _particle_tex: Texture2D = null


## 从图集构建含 walk_/idle_ 四向动画的 SpriteFrames
static func build(texture: Texture2D, columns: int = 4) -> SpriteFrames:
	var frames := SpriteFrames.new()
	frames.remove_animation("default")
	for dir in ROW_OF:
		var row: int = ROW_OF[dir]
		var walk := "walk_%s" % dir
		frames.add_animation(walk)
		frames.set_animation_speed(walk, WALK_FPS)
		frames.set_animation_loop(walk, true)
		for col in columns:
			frames.add_frame(walk, _cut(texture, col, row))
		var idle := "idle_%s" % dir
		frames.add_animation(idle)
		frames.set_animation_speed(idle, 1.0)
		frames.set_animation_loop(idle, true)
		frames.add_frame(idle, _cut(texture, 0, row))
	return frames


static func _cut(texture: Texture2D, col: int, row: int) -> AtlasTexture:
	var at := AtlasTexture.new()
	at.atlas = texture
	at.region = Rect2(col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H)
	return at


## 速度向量 → 朝向名（走/停通用）
static func dir_name(v: Vector2, fallback: String = "down") -> String:
	if v.length_squared() < 1.0:
		return fallback
	if absf(v.x) > absf(v.y):
		return "right" if v.x > 0 else "left"
	return "down" if v.y > 0 else "up"


# ---- W7 共享视觉件 ----------------------------------------------------------

## 径向渐变纹理（中心 from → 边缘 to），灯光与阴影共用
static func make_radial_tex(size: int, from: Color, to: Color) -> GradientTexture2D:
	var grad := Gradient.new()
	grad.set_color(0, from)
	grad.set_color(1, to)
	var tex := GradientTexture2D.new()
	tex.gradient = grad
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	tex.width = size
	tex.height = size
	return tex


## 脚下椭圆软阴影（w=阴影宽度像素；调用方挂为子节点即可）
static func make_shadow(w: float = 24.0) -> Sprite2D:
	if _shadow_tex == null:
		_shadow_tex = make_radial_tex(64, Color(0, 0, 0, 0.35), Color(0, 0, 0, 0))
	var sp := Sprite2D.new()
	sp.texture = _shadow_tex
	sp.scale = Vector2(w / 64.0, w / 64.0 * 0.45)   # 压扁成椭圆
	sp.show_behind_parent = true
	return sp


## UI 深色半透明 pill 面板样式（名牌/HUD 共用）
static func make_panel_style(bg := Color(0, 0, 0, 0.45)) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 6.0
	style.content_margin_right = 6.0
	style.content_margin_top = 2.0
	style.content_margin_bottom = 2.0
	return style


## CPU 粒子用 2×2 白点纹理（web Compatibility 不显式给 texture 可能不出图）
static func make_particle_tex() -> Texture2D:
	if _particle_tex == null:
		var img := Image.create(2, 2, false, Image.FORMAT_RGBA8)
		img.fill(Color.WHITE)
		_particle_tex = ImageTexture.create_from_image(img)
	return _particle_tex


## 通用 CPU 粒子构造（炊烟/萤火虫/花瓣/灰尘共用骨架）
static func make_particles(amount: int, lifetime: float) -> CPUParticles2D:
	var p := CPUParticles2D.new()
	p.texture = make_particle_tex()
	p.amount = amount
	p.lifetime = lifetime
	return p


## 气泡 Q 弹出现：wrap 从 0.6 倍回弹放大 + 打字机逐字
static func pop_bubble(wrap: Node2D, label: Label) -> void:
	wrap.visible = true
	wrap.modulate.a = 1.0
	wrap.scale = Vector2(0.6, 0.6)
	wrap.position.y = 0.0
	var tw := wrap.create_tween()
	tw.tween_property(wrap, "scale", Vector2.ONE, 0.18) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	# 打字机：逐字显出，长文封顶 2s
	var n := label.text.length()
	label.visible_characters = 0
	var tw2 := label.create_tween()
	tw2.tween_property(label, "visible_characters", n, clampf(n * 0.03, 0.2, 2.0))


## 气泡淡出消失：0.3s 渐隐 + 上浮，结束后隐藏
static func fade_bubble(wrap: Node2D) -> void:
	var tw := wrap.create_tween().set_parallel()
	tw.tween_property(wrap, "modulate:a", 0.0, 0.3)
	tw.tween_property(wrap, "position:y", wrap.position.y - 6.0, 0.3)
	tw.chain().tween_callback(func() -> void: wrap.visible = false)


## W9 气泡去重堆叠（核心算法，main 每帧调用）。
## owners 为「气泡宿主」，须实现 duck-typed：bubble_visible()->bool /
## set_bubble_lift(px) / bubble_global_rect()->Rect2 / 属性 global_position。
## 按宿主屏幕 y 升序处理：上方角色留基准位，下方气泡与已放置者重叠则上顶，
## 直至互不相交（标准 AABB 错开），消除多气泡叠成一团。
static func declutter_bubbles(owners: Array, gap := 6.0) -> void:
	var vis: Array = []
	for o in owners:
		if o.bubble_visible():
			vis.append(o)
	if vis.size() < 2:
		if vis.size() == 1:
			vis[0].set_bubble_lift(0.0)
		return
	vis.sort_custom(func(a, b): return a.global_position.y < b.global_position.y)
	var placed: Array = []          # 已定位气泡的全局 Rect2
	for o in vis:
		o.set_bubble_lift(0.0)      # 先归零取基准矩形
		var r: Rect2 = o.bubble_global_rect()
		var lift := 0.0
		var guard := 0
		while guard < 8:
			guard += 1
			var bumped := false
			for pr in placed:
				if r.intersects(pr):
					var new_top: float = pr.position.y - r.size.y - gap
					lift += r.position.y - new_top
					r.position.y = new_top
					bumped = true
			if not bumped:
				break
		o.set_bubble_lift(lift)
		placed.append(r)
