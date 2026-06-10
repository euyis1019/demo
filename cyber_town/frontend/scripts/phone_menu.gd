extends CanvasLayer
## 类手机菜单（方案 D9/D18/§7.5）：当面说 / 私聊(每 NPC 会话) / 群聊 / 记录。
## PC 游戏内拟物 UI——Tab 呼出，走近 NPC 按 E 直达其私聊页（由 main 调 open_private）。
## 呈现分工（D18）：当面说类消息实时头顶气泡 + 全部进记录；私聊/群聊只进面板+角标+提示音。

signal speak_requested(content: String)          # 当面说（main 负责本地气泡回显）

const PHONE_SIZE := Vector2(390, 600)

var player_id := -1
var names := {}                  # agent_id(int) -> 显示名
var groups := []                 # [{group_id, name, members}]
var contacts_cache := []         # 最近一帧快照的 contacts
var affinity_to_player := {}     # npc_id(int) -> score（M4，快照 agents 携带）

var _root: Control
var _tabs: TabContainer
var _unread := {"private": 0, "group": 0}

# 会话存储：私聊 per-NPC，群聊 per-group，当面说/记录为全局流。
# 不变量：_private_logs[npc_id] = 与该 NPC 的整段会话（无论方向）——
#   收到的消息按 sender_id 入键、发出/失败的按 recipient_id 入键，两者都是对方 id。
var _private_logs := {}          # npc_id -> Array[String(bbcode行)]
var _group_logs := {}            # group_id -> Array（本期只渲染 groups[0]，多群渲染留 §14 扩展）
var _local_log := []             # 当面说页（在场对话流：自己+别人+旁听）
var _archive := []               # 记录页（全渠道留档）
# 去重键带渠道前缀：同一 message_id 会同时出现在 direct_message 与 overhear
# 两表（F2F 设计如此，overhear 外键引用同 id），"d:"/"o:" 分开互不串扰；
# 本节点跨重连不销毁，_seen_ids 同时兜住后端游标重置时的历史重推。
var _seen_ids := {}              # "d:<id>" / "o:<id>" -> true

var _active_private := -1        # 当前私聊对象
var _notify: AudioStreamPlayer

# UI 引用
var _local_history: RichTextLabel
var _local_present: Label
var _local_input: LineEdit
var _local_send_btn: Button
var _contact_list: ItemList
var _private_history: RichTextLabel
var _private_title: Label
var _private_input: LineEdit
var _group_history: RichTextLabel
var _group_input: LineEdit
var _archive_view: RichTextLabel


func _ready() -> void:
	layer = 10
	_notify = AudioStreamPlayer.new()
	_notify.stream = load("res://assets/audio/notify.wav")
	_notify.volume_db = -8.0
	add_child(_notify)
	_build_ui()
	_root.visible = false


# ====================== 对外接口（main 调用） ======================

func toggle() -> void:
	if _root.visible:
		close()
	else:
		open()


func open(tab: int = -1) -> void:
	_root.visible = true
	_root.add_to_group("ui_blocking")     # player.gd 据此停走
	if tab >= 0:
		_tabs.current_tab = tab
	_refresh_badges()


func close() -> void:
	_root.visible = false
	_root.remove_from_group("ui_blocking")


func is_open() -> bool:
	return _root.visible


## 按 E 直达：打开菜单并切到指定 NPC 的私聊会话
func open_private(npc_id: int) -> void:
	_active_private = npc_id
	open(1)
	_select_contact_row(npc_id)
	_render_private()
	_private_input.grab_focus()


## 每帧快照灌入：消息分拣 / 联系人刷新 / 角标与提示音
func ingest_snapshot(data: Dictionary) -> void:
	contacts_cache = data.get("contacts", [])
	# M4：NPC 对玩家的好感（agents 分片携带），联系人列表显示爱心
	var agents: Dictionary = data.get("agents", {})
	for aid_str in agents:
		var sc: Variant = (agents[aid_str] as Dictionary).get("affinity_to_player")
		if sc != null:
			affinity_to_player[int(aid_str)] = int(sc)
	_refresh_contacts()
	var pv: Dictionary = data.get("player_view", {})
	var got_private := false
	var got_group := false

	for m in pv.get("f2f", []):
		if _mark_seen("d", m):
			var line := _fmt(m.get("sender_id"), str(m.get("content", "")))
			_local_log.append(line)
			_archive.append("[color=#88c]🗣[/color] " + line)
	for m in pv.get("overheard", []):
		if _mark_seen("o", m):
			var line := _fmt(m.get("sender_id"), str(m.get("content", "")))
			_local_log.append("[color=#999](旁听) [/color]" + line)
			_archive.append("[color=#999]👂 (旁听) [/color]" + line)
	for m in pv.get("incoming", []):
		if _mark_seen("d", m):
			var sid := int(m.get("sender_id", -1))
			_private_logs.get_or_add(sid, []).append(
				_fmt(sid, str(m.get("content", ""))))
			_archive.append("[color=#8c8]📨[/color] " + _fmt(sid, str(m.get("content", ""))))
			got_private = true
	for m in pv.get("group", []):
		if _mark_seen("d", m):
			var gid := int(m.get("group_id", 0))
			var line := _fmt(m.get("sender_id"), str(m.get("content", "")))
			_group_logs.get_or_add(gid, []).append(line)
			_archive.append("[color=#c9c]👥[%s][/color] " % str(m.get("group_name", gid)) + line)
			got_group = true
	for m in pv.get("failed", []):
		if _mark_seen("d", m):
			var who := _name_of(int(m.get("recipient_id", -1)))
			var why := str(m.get("reason", "不可达"))
			var note := "[color=#e66]⚠ 给 %s 的消息未送达（%s）[/color]" % [who, why]
			_archive.append(note)
			_private_logs.get_or_add(int(m.get("recipient_id", -1)), []).append(note)

	# 角标与提示音：菜单关着或不在对应页时累计未读
	if got_private and (not _root.visible or _tabs.current_tab != 1):
		_unread["private"] += 1
		_notify.play()
	if got_group and (not _root.visible or _tabs.current_tab != 2):
		_unread["group"] += 1
		_notify.play()
	_refresh_badges()
	_render_all()


## 当面说可用性（玩家移动 pending 时由 main 置灰，方案 §7.2）
func set_local_enabled(enabled: bool, present_names: Array) -> void:
	_local_input.editable = enabled
	_local_send_btn.disabled = not enabled  # 视觉与行为一致（审查 UX-001）
	_local_input.placeholder_text = "对在场的人说…" if enabled else "正在赶路，到了再说话"
	_local_present.text = ("在场：" + "、".join(present_names)) if present_names.size() > 0 \
		else "在场：只有你自己（说了也没人听见）"


# ====================== 内部：发送 ======================

func _send_local() -> void:
	var text := _local_input.text.strip_edges()
	if text == "" or not _local_input.editable:
		return
	if WorldNet.send_speak_to_local(text):
		_local_input.text = ""
		var line := "[color=#fc6]我[/color]：%s" % text
		_local_log.append(line)
		_archive.append("[color=#88c]🗣[/color] " + line)
		speak_requested.emit(text)        # main → player.show_bubble 本地即时回显
		_render_all()


func _send_private() -> void:
	var text := _private_input.text.strip_edges()
	if text == "" or _active_private < 0:
		return
	if WorldNet.send_private_message(_active_private, text):
		_private_input.text = ""
		var line := "[color=#fc6]我[/color]：%s" % text
		_private_logs.get_or_add(_active_private, []).append(line)
		_archive.append("[color=#8c8]📨(发给 %s)[/color] %s" % [_name_of(_active_private), line])
		_render_all()


func _send_group() -> void:
	var text := _group_input.text.strip_edges()
	if text == "" or groups.is_empty():
		return
	var gid := int(groups[0].get("group_id", 100))
	if WorldNet.send_to_group(gid, text):
		_group_input.text = ""
		var line := "[color=#fc6]我[/color]：%s" % text
		_group_logs.get_or_add(gid, []).append(line)
		_archive.append("[color=#c9c]👥[/color] " + line)
		_render_all()


# ====================== 内部：渲染 ======================

func _render_all() -> void:
	_local_history.text = "\n".join(_tail(_local_log, 60))
	_render_private()
	var gid := int(groups[0].get("group_id", 100)) if not groups.is_empty() else 100
	_group_history.text = "\n".join(_tail(_group_logs.get(gid, []), 60))
	_archive_view.text = "\n".join(_tail(_archive, 120))


func _render_private() -> void:
	if _active_private >= 0:
		_private_title.text = "与 %s 的私聊" % _name_of(_active_private)
		_private_history.text = "\n".join(_tail(_private_logs.get(_active_private, []), 60))
	else:
		_private_title.text = "← 先在左侧选一位联系人"
		_private_history.text = ""


func _refresh_contacts() -> void:
	_contact_list.clear()
	for c in contacts_cache:
		var aid := int(c.get("agent_id", -1))
		var label := str(c.get("name", _name_of(aid)))
		if affinity_to_player.has(aid):
			label += "  %s%d" % [_heart_of(int(affinity_to_player[aid])), int(affinity_to_player[aid])]
		var reachable: bool = bool(c.get("can_reach_now", false))
		var idx := _contact_list.add_item(label + ("" if reachable else "（不可达）"))
		_contact_list.set_item_metadata(idx, aid)
		_contact_list.set_item_disabled(idx, not reachable)
		if not reachable and c.get("reason") != null:
			_contact_list.set_item_tooltip(idx, str(c.get("reason")))


func _select_contact_row(npc_id: int) -> void:
	for i in _contact_list.item_count:
		if int(_contact_list.get_item_metadata(i)) == npc_id:
			_contact_list.select(i)
			return


func _refresh_badges() -> void:
	if _tabs.get_tab_count() < 4:
		return  # 构建期防御：tabs 未建齐
	if _root.visible:
		if _tabs.current_tab == 1:
			_unread["private"] = 0
		if _tabs.current_tab == 2:
			_unread["group"] = 0
	_tabs.set_tab_title(0, "当面说")
	_tabs.set_tab_title(1, "私聊" + _badge(_unread["private"]))
	_tabs.set_tab_title(2, "群聊" + _badge(_unread["group"]))
	_tabs.set_tab_title(3, "记录")


# ====================== 工具 ======================

func _badge(n: int) -> String:
	return "" if n <= 0 else "（%d）" % n


func _heart_of(score: int) -> String:
	## 好感爱心：陌生🤍 熟悉/友好❤ 亲密/挚友❤❤（与后端 5 档阈值对齐）
	if score >= 60:
		return "❤❤"
	if score >= 20:
		return "❤"
	return "🤍"


func _name_of(aid: int) -> String:
	return str(names.get(aid, "村民%d" % aid))


func _fmt(sender: Variant, content: String) -> String:
	var sid := int(sender) if sender != null else -1
	var who := "我" if sid == player_id else _name_of(sid)
	return "[color=#9cf]%s[/color]：%s" % [who, content]


func _mark_seen(prefix: String, m: Dictionary) -> bool:
	var key := "%s:%s" % [prefix, str(m.get("message_id", ""))]
	if _seen_ids.has(key):
		return false
	_seen_ids[key] = true
	return true


func _tail(arr: Array, n: int) -> Array:
	return arr.slice(maxi(0, arr.size() - n))


# ====================== UI 构建 ======================

func _build_ui() -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)

	var phone := PanelContainer.new()
	phone.custom_minimum_size = PHONE_SIZE
	# 显式锚点+偏移：贴屏幕右缘内 24px、垂直居中（勿用 preset+position 叠加——
	# position 是父坐标系绝对值，负值会把面板顶出屏幕，审查 GDAPI-003）
	phone.anchor_left = 1.0
	phone.anchor_right = 1.0
	phone.anchor_top = 0.5
	phone.anchor_bottom = 0.5
	phone.offset_left = -PHONE_SIZE.x - 24
	phone.offset_right = -24
	phone.offset_top = -PHONE_SIZE.y / 2
	phone.offset_bottom = PHONE_SIZE.y / 2
	phone.mouse_filter = Control.MOUSE_FILTER_STOP
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.09, 0.1, 0.14, 0.96)
	style.corner_radius_top_left = 18
	style.corner_radius_top_right = 18
	style.corner_radius_bottom_left = 18
	style.corner_radius_bottom_right = 18
	style.border_width_left = 3
	style.border_width_right = 3
	style.border_width_top = 3
	style.border_width_bottom = 3
	style.border_color = Color(0.25, 0.27, 0.35)
	style.content_margin_left = 10.0
	style.content_margin_right = 10.0
	style.content_margin_top = 8.0
	style.content_margin_bottom = 10.0
	phone.add_theme_stylebox_override("panel", style)
	_root.add_child(phone)

	var vbox := VBoxContainer.new()
	phone.add_child(vbox)

	var title := Label.new()
	title.text = "📱 小镇通    （Tab/Esc 收起）"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 15)
	vbox.add_child(title)

	_tabs = TabContainer.new()
	_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(_tabs)

	_tabs.add_child(_build_local_tab())
	_tabs.add_child(_build_private_tab())
	_tabs.add_child(_build_group_tab())
	_tabs.add_child(_build_archive_tab())
	# 信号必须在全部 tab 建好之后再连——add 首个 tab 即触发 tab_changed，
	# 彼时 set_tab_title(1..3) 会越界（headless 实测抓到的 child null 错误）
	_tabs.tab_changed.connect(func(_i: int) -> void: _refresh_badges())
	_refresh_badges()


func _build_local_tab() -> Control:
	var box := VBoxContainer.new()
	box.name = "当面说"
	_local_present = Label.new()
	_local_present.add_theme_font_size_override("font_size", 12)
	box.add_child(_local_present)
	_local_history = _make_history()
	box.add_child(_local_history)
	var row := HBoxContainer.new()
	_local_input = LineEdit.new()
	_local_input.placeholder_text = "对在场的人说…"
	_local_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_local_input.text_submitted.connect(func(_t: String) -> void: _send_local())
	row.add_child(_local_input)
	_local_send_btn = Button.new()
	_local_send_btn.text = "说"
	_local_send_btn.pressed.connect(_send_local)
	row.add_child(_local_send_btn)
	box.add_child(row)
	return box


func _build_private_tab() -> Control:
	var box := VBoxContainer.new()
	box.name = "私聊"
	_contact_list = ItemList.new()
	_contact_list.custom_minimum_size = Vector2(0, 96)
	_contact_list.item_selected.connect(func(i: int) -> void:
		_active_private = int(_contact_list.get_item_metadata(i))
		_render_private())
	box.add_child(_contact_list)
	_private_title = Label.new()
	_private_title.add_theme_font_size_override("font_size", 12)
	box.add_child(_private_title)
	_private_history = _make_history()
	box.add_child(_private_history)
	var row := HBoxContainer.new()
	_private_input = LineEdit.new()
	_private_input.placeholder_text = "发条私信（对方手机上收到）…"
	_private_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_private_input.text_submitted.connect(func(_t: String) -> void: _send_private())
	row.add_child(_private_input)
	var btn := Button.new()
	btn.text = "发"
	btn.pressed.connect(_send_private)
	row.add_child(btn)
	box.add_child(row)
	return box


func _build_group_tab() -> Control:
	var box := VBoxContainer.new()
	box.name = "群聊"
	_group_history = _make_history()
	box.add_child(_group_history)
	var row := HBoxContainer.new()
	_group_input = LineEdit.new()
	_group_input.placeholder_text = "在「镇民群」里说…"
	_group_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_group_input.text_submitted.connect(func(_t: String) -> void: _send_group())
	row.add_child(_group_input)
	var btn := Button.new()
	btn.text = "发"
	btn.pressed.connect(_send_group)
	row.add_child(btn)
	box.add_child(row)
	return box


func _build_archive_tab() -> Control:
	var box := VBoxContainer.new()
	box.name = "记录"
	_archive_view = _make_history()
	box.add_child(_archive_view)
	return box


func _make_history() -> RichTextLabel:
	var rtl := RichTextLabel.new()
	rtl.bbcode_enabled = true
	rtl.scroll_following = true
	rtl.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rtl.add_theme_font_size_override("normal_font_size", 13)
	return rtl
