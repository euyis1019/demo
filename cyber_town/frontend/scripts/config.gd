extends Node
## 全局配置（autoload: Config）——世界布局 / 服务器地址 / 视觉参数。
## 引擎只有离散 place，地点内坐标全是前端表现层（方案 §7.2/C4）。

## 服务器地址：桌面运行连本机后端；Web 导出版自适应当前页面 host
## （浏览器里游戏由 FastAPI 静态托管，与 WS/REST 同源）。
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

## 三个地点的世界矩形（像素坐标，决定 zone 触发与地面绘制）
const ZONES := {
	"farm":   Rect2(60, 120, 420, 460),
	"square": Rect2(580, 120, 420, 460),
	"saloon": Rect2(1100, 120, 420, 460),
}

const ZONE_NAMES := {"farm": "农场", "square": "广场", "saloon": "酒馆"}

## ====== Ninja Adventure（CC0）视觉资产 ======
## tileset.png 16px 网格；以下坐标均已对网格标注图逐块目检，截图迭代校正。
const NA_TILESET := "res://assets/gfx/na/tileset.png"

## 地面 tile（atlas 格坐标 col,row；程序化按色相+方差筛纯色块后人工确认）
const T_GRASS := Vector2i(22, 22)            # 满块草基底（带细纹理，无透明边）
const T_DECO := [Vector2i(9, 15), Vector2i(12, 15)]  # 点缀层：草丛/花（带透明边，叠在基底上）
const DECO_RATE := 0.06                      # 点缀密度
const T_SAND := Vector2i(14, 13)     # 橙砂（广场地面）
const T_DIRT := Vector2i(1, 15)      # 泥土（小路）

## 大块物件（tileset.png 内像素 region；对照 /tmp/na_part{A,B}.png 标注图逐块读数）
const NA_PROPS := {
	"house_thatch": Rect2(0, 0, 64, 80),     # 茅草屋（农家）
	"house_door":   Rect2(128, 0, 64, 80),   # 茅草屋带门
	"house_red":    Rect2(192, 0, 76, 80),   # 红瓦大屋（酒馆主体，和风）
	"house_dome":   Rect2(256, 0, 48, 64),   # 圆顶茅屋（杂货铺）
	"torii":        Rect2(0, 64, 32, 48),    # 鸟居
	"fence":        Rect2(96, 432, 48, 16),  # 深色尖木栅栏
	"pond":         Rect2(288, 96, 76, 76),  # 池塘（橙圈蓝水）
	"bush":         Rect2(0, 96, 32, 32),    # 圆灌木
	"tree_round":   Rect2(64, 128, 32, 48),  # 圆冠绿树
	"pine":         Rect2(128, 128, 32, 48), # 深绿杉
	"cart":         Rect2(80, 120, 32, 40),  # 红篷货车（单辆）
	"jar":          Rect2(16, 96, 16, 16),   # 陶罐/酒坛
	"sakura":       Rect2(64, 208, 64, 48),  # 樱花树簇
	"field":        Rect2(400, 240, 48, 32), # 田畦（草上棕土块）
}

## 物件布置（name, 世界坐标中心；避开 NPC 锚点与玩家通行带）
const NA_PLACEMENTS := [
	# —— 农场：茅草农舍 + 三排田畦 + 木栏 ——
	["house_thatch", Vector2(180, 215)],
	["field", Vector2(140, 345)], ["field", Vector2(252, 345)],
	["field", Vector2(140, 425)], ["field", Vector2(252, 425)],
	["field", Vector2(140, 505)], ["field", Vector2(252, 505)],
	["fence", Vector2(120, 565)], ["fence", Vector2(216, 565)], ["fence", Vector2(312, 565)], ["fence", Vector2(408, 565)],
	["tree_round", Vector2(420, 210)], ["bush", Vector2(380, 285)],
	["jar", Vector2(255, 250)],
	# —— 广场：池塘 + 鸟居 + 樱花 + 圆顶杂货铺 + 货车 ——
	["pond", Vector2(790, 280)],
	["torii", Vector2(620, 195)],
	["tree_round", Vector2(950, 180)], ["bush", Vector2(905, 215)],
	["house_dome", Vector2(930, 505)],
	["jar", Vector2(645, 540)], ["jar", Vector2(668, 552)], ["bush", Vector2(620, 555)],
	["bush", Vector2(700, 165)],
	# —— 酒馆：红瓦大屋 + 门口酒坛 + 树 ——
	["house_red", Vector2(1300, 235)],
	["jar", Vector2(1235, 360)], ["jar", Vector2(1262, 372)], ["jar", Vector2(1368, 365)],
	["pine", Vector2(1465, 205)], ["tree_round", Vector2(1150, 200)],
	["bush", Vector2(1175, 520)], ["fence", Vector2(1300, 565)],
	# —— 林缘野地点缀 ——
	["pine", Vector2(300, 70)], ["tree_round", Vector2(360, 80)],
	["pine", Vector2(525, 320)], ["tree_round", Vector2(545, 625)],
	["pine", Vector2(1050, 415)], ["pine", Vector2(1540, 645)],
	["tree_round", Vector2(1090, 660)], ["pine", Vector2(60, 660)],
	["bush", Vector2(520, 485)], ["bush", Vector2(1060, 175)], ["bush", Vector2(820, 665)],
]

## 角色精灵映射（agent_id → Ninja Adventure 角色图；16×28，4列走帧×4行方向）
const NA_CHARS := {
	0: "res://assets/gfx/na/char_5.png",   # 玩家＝草帽农夫
	1: "res://assets/gfx/na/char_9.png",   # 老钱＝白须老者
	2: "res://assets/gfx/na/char_12.png",  # 阿香＝黑发红衣女
	3: "res://assets/gfx/na/char_2.png",   # 大山＝橙衣壮汉
}
const NA_FACES := {
	0: "res://assets/gfx/na/face_5.png", 1: "res://assets/gfx/na/face_9.png",
	2: "res://assets/gfx/na/face_12.png", 3: "res://assets/gfx/na/face_2.png",
}

## 每个地点的站位锚点（NPC 到达后的落点 + 游走圆心），按到场顺序轮用
const ANCHORS := {
	"farm":   [Vector2(200, 330), Vector2(320, 420), Vector2(150, 470), Vector2(380, 280)],
	"square": [Vector2(740, 330), Vector2(860, 420), Vector2(680, 470), Vector2(900, 280)],
	"saloon": [Vector2(1260, 330), Vector2(1380, 420), Vector2(1200, 470), Vector2(1420, 280)],
}

const PLAYER_SPEED := 150.0      # 玩家步速（px/s）
const NPC_SPEED := 70.0          # NPC 跨地点步行速度
const NPC_WANDER_RADIUS := 56.0  # NPC 在锚点附近游走半径
const BUBBLE_SECONDS := 5.0      # 头顶气泡显示时长
const SPRITE_SCALE := 2.0        # 地面/物件放大倍数（16px tile → 32px）
const CHAR_SCALE := 3.0          # 角色放大倍数（16×16 帧 → 48px，约 1.5 格高）

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
