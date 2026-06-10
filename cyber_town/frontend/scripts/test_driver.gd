extends Node
## UI 测试驾驶员（回归用，autoload）：仅当环境变量 CT_UITEST=1 时激活，
## 正常游玩零影响。模拟真实用户旅程（按键走真实输入路径；打字走白盒注入），
## 沿途把截图存到 CT_UITEST_DIR（默认 /tmp/ct_ui），结束自动退出。
##
## 运行：CT_UITEST=1 /Applications/Godot.app/Contents/MacOS/Godot --path cyber_town/frontend

var _out := "/tmp/ct_ui"


func _ready() -> void:
	if OS.get_environment("CT_UITEST") != "1":
		return
	var dir := OS.get_environment("CT_UITEST_DIR")
	if dir != "":
		_out = dir
	DirAccess.make_dir_recursive_absolute(_out)
	print("[UITEST] 启动，截图目录：", _out)
	_run()


func _run() -> void:
	await _sleep(2.5)                              # 连接 + 首帧快照落位
	await _shot("01_initial_farm")

	# —— 按 E 直达私聊（大山就在身旁，真实按键路径）——
	_tap_key(KEY_E)
	await _sleep(0.6)
	await _shot("02_press_e_private")
	_tap_key(KEY_ESCAPE)
	await _sleep(0.4)

	# —— 当面说：本地即时回显 + 等真实 LLM 回话 ——
	var main := get_tree().current_scene
	main.phone.open(0)
	main.phone._local_input.text = "大山哥，我刚搬来，地里的事多多指教！"
	main.phone._send_local()
	await _sleep(0.5)
	await _shot("03_speak_local_echo")
	await _sleep(9.0)                              # 2-3 拍真实 LLM
	await _shot("04_npc_reply")
	_tap_key(KEY_TAB)                              # 收起菜单（真实按键）
	await _sleep(0.4)

	# —— 键盘走去广场（按住 D ≈3.8s，穿过 zone 边界触发 request_move）——
	_set_key(KEY_D, true)
	await _sleep(3.8)
	_set_key(KEY_D, false)
	await _sleep(6.0)                              # 拍末结算 + 确认
	await _shot("05_walk_to_square")

	# —— 群聊 ——
	main.phone.open(2)
	main.phone._group_input.text = "大家好，我是新来的农场主，多关照！"
	main.phone._send_group()
	await _sleep(0.5)
	await _shot("06_group_send")

	# —— 异地私聊阿香（RDC 1 拍延迟；她的回复要等心跳拍）——
	main.phone.open_private(2)
	main.phone._private_input.text = "阿香姐，晚上酒馆见！"
	main.phone._send_private()
	await _sleep(1.0)
	await _shot("07_private_and_hearts")
	_tap_key(KEY_ESCAPE)

	# —— 观察世界自主运转（心跳唤醒异地 NPC / 可能的回信）——
	await _sleep(22.0)
	main.phone.open(3)                             # 记录页总览
	await _sleep(0.5)
	await _shot("08_archive_world")

	print("[UITEST] DONE")
	await _sleep(0.5)
	get_tree().quit()


# ---- 工具 -------------------------------------------------------------

func _sleep(sec: float) -> void:
	await get_tree().create_timer(sec).timeout


func _shot(name_: String) -> void:
	await RenderingServer.frame_post_draw          # 保证拿到已渲染帧
	var img := get_viewport().get_texture().get_image()
	var path := "%s/%s.png" % [_out, name_]
	img.save_png(path)
	print("[UITEST] 截图 ", path)


func _set_key(keycode: Key, pressed: bool) -> void:
	var ev := InputEventKey.new()
	ev.keycode = keycode
	ev.physical_keycode = keycode
	ev.pressed = pressed
	Input.parse_input_event(ev)


func _tap_key(keycode: Key) -> void:
	_set_key(keycode, true)
	_set_key(keycode, false)
