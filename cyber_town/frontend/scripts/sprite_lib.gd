class_name SpriteLib
## 精灵帧工具：从网格图集运行时构建 SpriteFrames。
##
## 当前素材（Ninja Adventure，CC0）：16×16/帧（64×112 = 4 列走帧 × 7 行，
## 前 4 行为行走方向）。行序（截图迭代核实）：行0=下 / 行1=右 / 行2=上 / 行3=左。

const FRAME_W := 16
const FRAME_H := 16
const WALK_FPS := 7.0

const ROW_OF := {"down": 0, "right": 1, "up": 2, "left": 3}


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
