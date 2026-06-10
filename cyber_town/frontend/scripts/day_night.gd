extends CanvasModulate
## 日夜色调：按快照 world_time（HH:MM）在关键帧颜色间插值（方案 §7.6，纯前端表现）。

const KEYFRAMES := [
	# [分钟数, 色调]
	[5 * 60.0, Color(0.78, 0.74, 0.86)],     # 05:00 黎明（偏紫）
	[8 * 60.0, Color(1.0, 1.0, 1.0)],        # 08:00 白天
	[16 * 60.0, Color(1.0, 0.97, 0.9)],      # 16:00 午后暖
	[18 * 60.0, Color(1.0, 0.78, 0.6)],      # 18:00 黄昏（橙）
	[20 * 60.0, Color(0.45, 0.5, 0.72)],     # 20:00 夜
	[24 * 60.0, Color(0.32, 0.36, 0.58)],    # 24:00 深夜
	[29 * 60.0, Color(0.78, 0.74, 0.86)],    # (+05:00) 环回黎明
]


func set_world_time(hhmm: String) -> void:
	var parts := hhmm.split(":")
	if parts.size() != 2:
		return
	var minutes := float(int(parts[0]) * 60 + int(parts[1]))
	if minutes < 5 * 60.0:
		minutes += 24 * 60.0  # 0:00-5:00 落到环回段
	color = _interp(minutes)


func _interp(m: float) -> Color:
	for i in range(KEYFRAMES.size() - 1):
		var a: Array = KEYFRAMES[i]
		var b: Array = KEYFRAMES[i + 1]
		if m >= float(a[0]) and m <= float(b[0]):
			var k := (m - float(a[0])) / (float(b[0]) - float(a[0]))
			return (a[1] as Color).lerp(b[1] as Color, k)
	# 超界兜底：取最近的关键帧色而非突变白（异常时间字符串等场景）
	return KEYFRAMES[0][1] if m < float(KEYFRAMES[0][0]) else KEYFRAMES[-1][1]
