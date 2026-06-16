extends Node
## 全局配置（autoload: Config）——3D 版。服务器地址沿用 2D；地点布局改为 3D（XZ 平面）。
## 引擎只有离散 place，地点内坐标全是前端表现层；3D 把后端 Vector2 概念映射为 XZ。

# ---- 服务器地址（与 2D 同款，web 自适应同源）----
static func ws_url() -> String:
	if OS.has_feature("web"):
		var host := str(JavaScriptBridge.eval("location.host", true))
		var scheme := "wss" if str(JavaScriptBridge.eval("location.protocol", true)) == "https:" else "ws"
		return "%s://%s/ws/world" % [scheme, host]
	return "ws://127.0.0.1:8000/ws/world"


static func http_base() -> String:
	if OS.has_feature("web"):
		return str(JavaScriptBridge.eval("location.origin", true))
	return "http://127.0.0.1:8000"


# ---- 地形高度（单一真相源：地面网格 + 一切贴地物 y 全喂它）----
var _noise := FastNoiseLite.new()

func _ready() -> void:
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_noise.frequency = 0.03
	_noise.seed = 12345

func height(x: float, z: float) -> float:
	return _noise.get_noise_2d(x, z) * 0.5    # ±0.5 缓坡

func ground_y(xz: Vector2) -> float:
	return height(xz.x, xz.y)


# ---- 3D 世界布局（XZ 平面；三地点横向排布：农场左 / 广场中 / 酒馆右）----
const WORLD := Rect2(-44, -17, 88, 34)        # 地面范围（x,z）

## 地点矩形（XZ；玩家走进即触发 request_move，判定用内缩矩形做滞后）
const PLACE_RECTS := {
	"farm":   Rect2(-42, -15, 28, 30),
	"square": Rect2(-9, -13, 18, 26),
	"saloon": Rect2(14, -15, 28, 30),
}
const PLACE_NAMES := {"farm": "农场", "square": "广场", "saloon": "酒馆"}
const PLACE_CENTER := {
	"farm": Vector2(-28, 0), "square": Vector2(0, 0), "saloon": Vector2(28, 0),
}

## 各地点站位锚点（XZ；NPC 到达后落点 + 游走圆心，按到场顺序轮用）
const ANCHORS := {
	"farm":   [Vector2(-28, -2), Vector2(-24, 4), Vector2(-32, 3), Vector2(-26, -7)],
	"square": [Vector2(-2, -1), Vector2(3, 3), Vector2(-4, 4), Vector2(2, -4)],
	"saloon": [Vector2(26, -2), Vector2(30, 4), Vector2(22, 3), Vector2(28, -6)],
}

const PLAYER_SPAWN := Vector2(-28, 8)         # 农场出生（XZ）

# ---- 角色精灵（agent_id → Ninja Adventure 角色图，16×16 四向）----
const CHARS := {
	0: "res://assets/char_5.png",    # 玩家＝草帽农夫
	1: "res://assets/char_9.png",    # 老钱＝白须老者
	2: "res://assets/char_12.png",   # 阿香＝黑发红衣女
	3: "res://assets/char_2.png",    # 大山＝橙衣壮汉
}
const NPC_COLORS := {
	0: Color(0.55, 0.85, 0.55), 1: Color(0.95, 0.78, 0.30),
	2: Color(0.90, 0.45, 0.50), 3: Color(0.95, 0.60, 0.25),
}

# ---- 地形/植被纹理（spike 同款）----
const T_GRASS := "res://assets/grass.png"
const T_DIRT := "res://assets/dirt.png"
const T_TREE := "res://assets/tree.png"
const T_BLADE := "res://assets/blade.png"
const T_TUFT := "res://assets/grasstuft2.png"
const T_BLOB := "res://assets/blob.png"
const FLOWERS := ["res://assets/flower_red.png", "res://assets/flower_yellow.png",
	"res://assets/flower_white.png", "res://assets/flower_purple.png"]

# ---- 表现参数 ----
const CHAR_PX := 0.085           # AnimatedSprite3D.pixel_size（16px→约 1.36 单位）
const TREE_PX := 0.09
const PLAYER_SPEED := 7.0        # 玩家步速（单位/s）
const NPC_SPEED := 4.0           # NPC 跨/游走步速
const NPC_WANDER_RADIUS := 3.0
const E_TALK_DISTANCE := 5.0     # 按 E 直达私聊距离（单位）
const BUBBLE_SECONDS := 5.0
const CAM_SIZE := 13.0           # 正交相机视野高（单位）


## 某地点第 idx 个锚点（XZ；超出环形复用）
func anchor_of(place_id: String, idx: int) -> Vector2:
	var arr: Array = ANCHORS.get(place_id, [Vector2.ZERO])
	return arr[idx % arr.size()]


## XZ 点 → 所在地点 id（用内缩矩形做滞后，避免边界抖动）；不在任何地点返回 ""
func place_at(xz: Vector2, shrink := 0.0) -> String:
	for pid in PLACE_RECTS:
		if (PLACE_RECTS[pid] as Rect2).grow(-shrink).has_point(xz):
			return pid
	return ""
