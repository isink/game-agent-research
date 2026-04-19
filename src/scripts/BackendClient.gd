## BackendClient.gd
## Singleton — manages all communication with the Python FastAPI backend.
## Connects via WebSocket for real-time tick events,
## and sends HTTP requests for miracles and state queries.

extends Node

const BACKEND_URL := "http://127.0.0.1:8765"
const WS_URL      := "ws://127.0.0.1:8765/ws"

signal tick_received(tick_data: Dictionary)
signal connection_changed(connected: bool)

var _ws := WebSocketPeer.new()
var _is_connected  := false
var _auto_tick     := false
var _tick_interval := 5.0
var _tick_timer    := 0.0
var _retry_timer   := 0.0
const RETRY_INTERVAL := 3.0


func _ready() -> void:
	_connect_websocket()


func _process(delta: float) -> void:
	_ws.poll()
	var state := _ws.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			if not _is_connected:
				_is_connected = true
				connection_changed.emit(true)
			while _ws.get_available_packet_count() > 0:
				var packet := _ws.get_packet()
				var text   := packet.get_string_from_utf8()
				var parsed  = JSON.parse_string(text)
				if parsed is Dictionary:
					tick_received.emit(parsed as Dictionary)

		WebSocketPeer.STATE_CLOSED:
			if _is_connected:
				_is_connected = false
				connection_changed.emit(false)
			# Auto-reconnect
			_retry_timer += delta
			if _retry_timer >= RETRY_INTERVAL:
				_retry_timer = 0.0
				_ws = WebSocketPeer.new()
				_connect_websocket()

	# Auto-tick mode (for automated experiments)
	if _auto_tick:
		_tick_timer += delta
		if _tick_timer >= _tick_interval:
			_tick_timer = 0.0
			advance_tick()


# ── Public API ────────────────────────────────────────────────────────────

func advance_tick() -> void:
	"""Advance simulation one step. Result is broadcast via WebSocket."""
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result, _code, _headers, _body): http.queue_free())
	http.request(BACKEND_URL + "/tick", [], HTTPClient.METHOD_POST)


func inject_miracle(miracle_type: String, position: Array = []) -> void:
	"""Send a miracle event to the backend."""
	var body := JSON.stringify({"miracle_type": miracle_type, "position": position if position else null})
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result, _code, _headers, _body): http.queue_free())
	http.request(BACKEND_URL + "/miracle", ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)


func get_state(callback: Callable) -> void:
	"""Fetch current village state."""
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result, _code, _headers, body):
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary:
			callback.call(parsed as Dictionary)
		else:
			callback.call({})
		http.queue_free()
	)
	http.request(BACKEND_URL + "/state")


func get_research(callback: Callable) -> void:
	"""Fetch research metrics."""
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result, _code, _headers, body):
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary:
			callback.call(parsed as Dictionary)
		else:
			callback.call({})
		http.queue_free()
	)
	http.request(BACKEND_URL + "/research")


func set_auto_tick(enabled: bool, interval: float = 5.0) -> void:
	_auto_tick = enabled
	_tick_interval = interval
	_tick_timer = 0.0


func is_backend_connected() -> bool:
	return _is_connected


# ── Internal ───────────────────────────────────────────────────────────────

func _connect_websocket() -> void:
	_ws.connect_to_url(WS_URL)
