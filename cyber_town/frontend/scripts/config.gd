extends Node
## 全局配置（autoload: Config）——世界布局 / 服务器地址 / 视觉参数。
## 引擎只有离散 place，地点内坐标全是前端表现层（方案 §7.2/C4）。

const WS_URL := "ws://127.0.0.1:8000/ws/world"
const HTTP_BASE := "http://127.0.0.1:8000"   # REST（档案页 timeline 等）

## 三个地点的世界矩形（像素坐标，决定 zone 触发与地面绘制）
const ZONES := {
	"farm":   Rect2(60, 120, 420, 460),
	"square": Rect2(580, 120, 420, 460),
	"saloon": Rect2(1100, 120, 420, 460),
}

## 地点显示名与地面色（草地/石板/木地板的像素感基色）
const ZONE_NAMES := {"farm": "农场", "square": "广场", "saloon": "酒馆"}
const ZONE_COLORS := {
	"farm":   Color8(96, 153, 78),
	"square": Color8(158, 144, 116),
	"saloon": Color8(133, 94, 66),
}
const GRASS_BASE := Color8(74, 122, 62)   # 全图底色（zone 之间的野地）

## 每个地点的站位锚点（NPC 到达后的落点 + 游走圆心），按到场顺序轮用
const ANCHORS := {
	"farm":   [Vector2(200, 330), Vector2(320, 420), Vector2(150, 470), Vector2(380, 280)],
	"square": [Vector2(740, 330), Vector2(860, 420), Vector2(680, 470), Vector2(900, 280)],
	"saloon": [Vector2(1260, 330), Vector2(1380, 420), Vector2(1200, 470), Vector2(1420, 280)],
}

## 装饰物图集区域（Overworld.png 内像素 rect，坐标已逐块目检核实）
const DECOR_REGIONS := {
	"barn":     Rect2(176, 0, 80, 80),    # 大谷仓（农场）
	"house":    Rect2(96, 0, 64, 80),     # 小木屋（酒馆）
	"tree":     Rect2(80, 256, 32, 32),   # 大圆冠树
	"fountain": Rect2(352, 144, 48, 40),  # 喷泉（广场中心）
	"stall":    Rect2(288, 360, 72, 76),  # 蓝白集市摊（杂货铺）
	"crates":   Rect2(480, 0, 32, 32),    # 木箱
	"fence":    Rect2(32, 272, 48, 16),   # 木栅栏
}

## 装饰摆放（name, 世界坐标中心；已避开各地点 NPC 锚点与玩家通行带）
const DECOR_PLACEMENTS := [
	# —— 农场 ——
	["barn", Vector2(180, 220)],
	["fence", Vector2(150, 560)], ["fence", Vector2(246, 560)], ["fence", Vector2(342, 560)],
	["tree", Vector2(430, 210)],
	# —— 广场 ——
	["fountain", Vector2(790, 230)],
	["stall", Vector2(617, 585)],   # 左下角，避开锚点 (680,470)（×2 缩放后篷区勿盖站位）
	["crates", Vector2(960, 200)],
	["tree", Vector2(615, 185)],
	# —— 酒馆 ——
	["house", Vector2(1310, 230)],
	["crates", Vector2(1170, 530)], ["crates", Vector2(1450, 530)],
	["tree", Vector2(1465, 190)],
	# —— 野地点缀 ——
	["tree", Vector2(520, 320)], ["tree", Vector2(540, 640)],
	["tree", Vector2(1045, 420)], ["tree", Vector2(300, 70)],
	["tree", Vector2(820, 670)], ["tree", Vector2(1520, 660)],
]

const PLAYER_SPEED := 150.0      # 玩家步速（px/s）
const NPC_SPEED := 70.0          # NPC 跨地点步行速度
const NPC_WANDER_RADIUS := 56.0  # NPC 在锚点附近游走半径
const BUBBLE_SECONDS := 5.0      # 头顶气泡显示时长
const SPRITE_SCALE := 2.0        # 16x32 像素角色放大倍数

## 世界边界（相机限制）
const WORLD_RECT := Rect2(0, 0, 1600, 700)


## 玩家坐标 → 所在 zone 的 place_id；不在任何 zone 返回 ""
static func zone_at(pos: Vector2) -> String:
	for pid in ZONES:
		if (ZONES[pid] as Rect2).has_point(pos):
			return pid
	return ""


## 某地点第 idx 个锚点（超出环形复用）
static func anchor_of(place_id: String, idx: int) -> Vector2:
	var arr: Array = ANCHORS.get(place_id, [Vector2(800, 350)])
	return arr[idx % arr.size()]
