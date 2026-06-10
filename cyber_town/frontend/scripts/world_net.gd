extends Node
## WS 客户端（autoload: WorldNet）——连接后端 /ws/world，收快照、发命令。
##
## Godot 4 WebSocketPeer 正确用法（审查 A5）：_process 里先 poll()（只推进
## 连接状态机，不返回数据），再按 get_available_packet_count() 循环
## get_packet() 取包。断线指数退避重连；重连后用快照全量重建。

signal hello_received(data: Dictionary)
signal snapshot_received(frame: Dictionary)
signal ack_received(data: Dictionary)
signal error_received(data: Dictionary)
signal connection_changed(connected: bool)

var _socket := WebSocketPeer.new()
var _connected := false
var _client_seq := 0
var _retry_delay := 1.0          # 重连退避（秒），指数增长封顶 10s
var _retry_timer := 0.0
var _last_send := {}             # action -> 上次发送时刻（节流）

const SEND_THROTTLE := 0.3       # 同类命令最小间隔（方案 §7.4）


func _ready() -> void:
	_connect_to_server()


func _connect_to_server() -> void:
	var err := _socket.connect_to_url(Config.WS_URL)
	if err != OK:
		push_warning("WS 连接发起失败：%s，%.1fs 后重试" % [err, _retry_delay])


func _process(delta: float) -> void:
	_socket.poll()  # 只推进状态机
	var state := _socket.get_ready_state()
	match state:
		WebSocketPeer.STATE_OPEN:
			if not _connected:
				_connected = true
				_retry_delay = 1.0
				connection_changed.emit(true)
			while _socket.get_available_packet_count() > 0:
				_handle_packet(_socket.get_packet())
		WebSocketPeer.STATE_CLOSED:
			if _connected:
				_connected = false
				connection_changed.emit(false)
			_retry_timer += delta
			if _retry_timer >= _retry_delay:
				_retry_timer = 0.0
				_retry_delay = minf(_retry_delay * 2.0, 10.0)
				_socket = WebSocketPeer.new()  # CLOSED 的 peer 不能复用
				_connect_to_server()
		_:
			pass  # CONNECTING / CLOSING：等待


func _handle_packet(packet: PackedByteArray) -> void:
	var frame: Variant = JSON.parse_string(packet.get_string_from_utf8())
	if typeof(frame) != TYPE_DICTIONARY:
		push_warning("收到非 JSON 帧，忽略")
		return
	var data: Dictionary = frame.get("data", {})
	match frame.get("type", ""):
		"hello_ack":
			hello_received.emit(data)
		"snapshot":
			snapshot_received.emit(frame)  # 整帧透传（外层带 t/seq）
		"ack":
			ack_received.emit(data)
		"error":
			push_warning("服务端错误：%s" % [data])
			error_received.emit(data)
		_:
			pass


## 发一条玩家命令；返回 false 表示被节流或未连接
func send_command(action: String, kwargs: Dictionary) -> bool:
	if not _connected:
		return false
	var now := Time.get_ticks_msec() / 1000.0
	if now - float(_last_send.get(action, -10.0)) < SEND_THROTTLE:
		return false
	_last_send[action] = now
	_client_seq += 1
	_socket.send_text(JSON.stringify({
		"action": action, "client_seq": _client_seq, "kwargs": kwargs,
	}))
	return true


# ---- 四渠道便捷封装 -------------------------------------------------------

func send_request_move(place_id: String) -> bool:
	return send_command("request_move", {"place_id": place_id})

func send_speak_to_local(content: String) -> bool:
	return send_command("speak_to_local", {"content": content})

func send_private_message(target: int, content: String) -> bool:
	return send_command("send_message", {"target": target, "content": content})

func send_to_group(group_id: int, content: String) -> bool:
	return send_command("send_to_group", {"group_id": group_id, "content": content})
