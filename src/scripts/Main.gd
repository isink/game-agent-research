## Main.gd
## Root scene controller — God-game core loop.
##
## Game loop:
##   1. Player observes village, gathers faith from believers
##   2. Player spends faith to cast miracles
##   3. Villagers interpret miracles → distort → form beliefs
##   4. Beliefs produce faith; goal = unified religion
##
## Keyboard:
##   Space       — Advance one tick
##   A           — Toggle auto-tick
##   Tab         — Toggle research panel
##   Ctrl+E      — Export data

extends Node2D

@onready var backend:          Node            = $BackendClient
@onready var miracle_panel:    MiraclePanel    = $UI/MiraclePanel
@onready var research_panel:   PanelContainer  = $UI/ResearchPanel
@onready var status_label:     Label           = $UI/StatusLabel
@onready var tick_btn:         Button          = $UI/TickButton
@onready var auto_btn:         Button          = $UI/AutoButton
@onready var village_root:     Node2D          = $VillageRoot
@onready var village_bg:       Node2D          = $VillageRoot/VillageBackground
@onready var event_log:        RichTextLabel   = $UI/EventLog
@onready var speed_slider:     HSlider         = $UI/SpeedSlider
@onready var faith_label:      Label           = $UI/FaithLabel
@onready var objective_label:  Label           = $UI/ObjectiveLabel
@onready var flash_overlay:    ColorRect       = $UI/FlashOverlay

var villagers: Dictionary = {}
var current_tick: int      = 0
var auto_tick_enabled: bool = false

# ── Faith system ──────────────────────────────────────────────────────────────
var faith: float = 30.0
const FAITH_PER_BELIEVER := 1.5   # per tick, per believing villager
const FAITH_PER_TICK     := 0.3   # passive gain

# Log
const MAX_LOG_LINES := 40
var _log_lines: Array[String] = []

const VILLAGER_SCENE := preload("res://scenes/Villager.tscn")


func _ready() -> void:
	backend.tick_received.connect(_on_tick_received)
	backend.connection_changed.connect(_on_connection_changed)
	miracle_panel.miracle_requested.connect(_on_miracle_requested)
	research_panel.export_requested.connect(_on_export_requested)
	tick_btn.pressed.connect(_advance_tick)
	auto_btn.pressed.connect(_toggle_auto_tick)
	speed_slider.value_changed.connect(_on_speed_changed)

	flash_overlay.visible = false
	status_label.text     = "Connecting to backend…"
	event_log.text        = ""
	_update_faith_display()
	_update_objective(0, 0)

	await get_tree().create_timer(1.5).timeout
	backend.get_state(_on_initial_state_loaded)


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_SPACE:
				_advance_tick()
			KEY_A:
				_toggle_auto_tick()
			KEY_E when event.ctrl_pressed:
				_on_export_requested()


# ── Tick ───────────────────────────────────────────────────────────────────────

func _advance_tick() -> void:
	status_label.text = "Running tick %d…" % (current_tick + 1)
	backend.advance_tick()


func _toggle_auto_tick() -> void:
	auto_tick_enabled = not auto_tick_enabled
	var interval := lerpf(8.0, 1.0, (speed_slider.value - 1.0) / 9.0)
	backend.set_auto_tick(auto_tick_enabled, interval)
	auto_btn.text = "Auto: ON" if auto_tick_enabled else "Auto: OFF"


func _on_speed_changed(_v: float) -> void:
	if auto_tick_enabled:
		var interval := lerpf(8.0, 1.0, (speed_slider.value - 1.0) / 9.0)
		backend.set_auto_tick(true, interval)


func _on_tick_received(data: Dictionary) -> void:
	current_tick = data.get("tick", current_tick)
	status_label.text = "Tick %d" % current_tick

	# Count believers for faith calc
	var total_believers: int = 0

	# Update villagers
	var agent_states = data.get("agent_states", [])
	if agent_states is Array:
		for agent_data in agent_states:
			if not agent_data is Dictionary:
				continue
			var aid: String = agent_data.get("agent_id", "")
			if villagers.has(aid):
				villagers[aid].update_from_state(agent_data)
				total_believers += villagers[aid].get_belief_count()

	# Faith income
	faith += FAITH_PER_TICK + total_believers * FAITH_PER_BELIEVER
	miracle_panel.set_faith(faith)
	_update_faith_display()
	_update_objective(total_believers, villagers.size())

	# Miracle
	var miracle = data.get("miracle")
	if miracle is Dictionary and miracle.size() > 0:
		var witnesses = miracle.get("witnesses", [])
		if witnesses is Array:
			for witness_id in witnesses:
				if villagers.has(witness_id):
					villagers[witness_id].highlight_as_witness()
		var pos_arr = miracle.get("position", [5, 4])
		if pos_arr is Array and pos_arr.size() >= 2:
			village_bg.flash_miracle(Vector2i(int(pos_arr[0]), int(pos_arr[1])))
		_miracle_screen_flash()
		status_label.text = "⚡ %s — Tick %d" % [
			miracle.get("type", "miracle"), current_tick,
		]
		_log("[color=#f0c040]⚡ MIRACLE:[/color] %s" % miracle.get("description", ""))

	# Conversations
	var conversations = data.get("conversations", [])
	if conversations is Array:
		for conv in conversations:
			if not conv is Dictionary:
				continue
			var drift: float = conv.get("semantic_drift", 0.0)
			var action: String = conv.get("action_type", "share_rumor")
			var icon: String = _action_icon(action)
			var color: String = "#ff8888" if drift > 0.25 else "#aaaaaa"
			_log("[color=%s]%s %s → %s[/color]  drift=%.3f" % [
				color, icon,
				conv.get("sender", "?"), conv.get("receiver", "?"), drift,
			])

	# Reflections
	var reflections = data.get("reflections", [])
	if reflections is Array:
		for ref in reflections:
			if not ref is Dictionary:
				continue
			var aname: String = ref.get("agent", "?")
			_log("[color=#cc88ff]🔮 %s reflects[/color]" % aname)
			var beliefs_dict = ref.get("beliefs", {})
			if beliefs_dict is Dictionary:
				for bval in beliefs_dict.values():
					_log("  [color=#bbaaff]🙏 %s[/color]" % str(bval).left(80))
			var procs = ref.get("procedures", [])
			if procs is Array:
				for proc in procs:
					_log("  [color=#88ffaa]⚙ %s[/color]" % str(proc).left(80))

	research_panel.update_from_tick(data)


# ── Miracle ────────────────────────────────────────────────────────────────────

func _on_miracle_requested(miracle_type: String) -> void:
	var cost: int = miracle_panel.get_miracle_cost(miracle_type)
	if faith < cost:
		return
	faith -= cost
	_update_faith_display()
	miracle_panel.set_faith(faith)
	backend.inject_miracle(miracle_type)
	status_label.text = "⚡ %s sent…" % miracle_type
	_log("[color=#f0c040]▶ Miracle: %s (-%d✝)[/color]" % [miracle_type, cost])


func _miracle_screen_flash() -> void:
	"""Full-screen flash + shake when miracle lands."""
	flash_overlay.visible = true
	flash_overlay.color   = Color(1.0, 0.95, 0.6, 0.5)

	var tw := create_tween()
	tw.tween_property(flash_overlay, "color:a", 0.0, 0.6).set_ease(Tween.EASE_OUT)
	tw.tween_callback(func() -> void: flash_overlay.visible = false)

	# Screen shake
	var orig_pos: Vector2 = village_root.position
	var shake_tw := create_tween()
	for i in range(6):
		var offset := Vector2(randf_range(-4, 4), randf_range(-4, 4))
		shake_tw.tween_property(village_root, "position", orig_pos + offset, 0.04)
	shake_tw.tween_property(village_root, "position", orig_pos, 0.06)


# ── Initial load ───────────────────────────────────────────────────────────────

func _on_initial_state_loaded(data: Dictionary) -> void:
	if not data or not data.has("agents"):
		status_label.text = "ERROR: Backend unreachable. Run: python server.py"
		return
	var agents: Array = data.get("agents", [])
	for agent_data in agents:
		_spawn_villager(agent_data)
	status_label.text = "Village loaded — %d villagers" % agents.size()
	_log("[color=#88ccff]Village initialized — %d agents[/color]" % agents.size())


func _spawn_villager(data: Dictionary) -> void:
	var villager: Villager = VILLAGER_SCENE.instantiate()
	village_root.add_child(villager)
	villager.setup(data)
	villagers[data.get("agent_id", "")] = villager


# ── Faith display ──────────────────────────────────────────────────────────────

func _update_faith_display() -> void:
	faith_label.text = "✝ Faith: %d" % int(faith)


func _update_objective(believers: int, total: int) -> void:
	if total == 0:
		objective_label.text = "Goal: Awaken belief in all villagers"
	elif believers >= total:
		objective_label.text = "✦ All villagers believe! Keep the faith growing."
	elif believers > 0:
		objective_label.text = "Believers: %d / %d — Cast miracles to spread belief" % [believers, total]
	else:
		objective_label.text = "No believers yet — Cast a miracle to begin"


# ── Export ─────────────────────────────────────────────────────────────────────

func _on_export_requested() -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_r, _c, _h, body: PackedByteArray) -> void:
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary:
			var result: Dictionary = parsed
			status_label.text = "✓ Exported: %s" % result.get("exported_to", "?")
			_log("[color=#88ffaa]✓ Exported[/color]")
		http.queue_free()
	)
	http.request("http://127.0.0.1:8765/export")


# ── Event log ──────────────────────────────────────────────────────────────────

func _log(line: String) -> void:
	_log_lines.append(line)
	if _log_lines.size() > MAX_LOG_LINES:
		_log_lines = _log_lines.slice(_log_lines.size() - MAX_LOG_LINES)
	event_log.text = "\n".join(_log_lines)
	(func() -> void: event_log.scroll_to_line(event_log.get_line_count() - 1)).call_deferred()


# ── Connection ─────────────────────────────────────────────────────────────────

func _on_connection_changed(connected: bool) -> void:
	if connected:
		status_label.text = "Backend connected."
		_log("[color=#88ffaa]✓ Connected[/color]")
	else:
		status_label.text = "Backend disconnected. Retrying…"


# ── Helpers ────────────────────────────────────────────────────────────────────

static func _action_icon(action: String) -> String:
	match action:
		"warn":            return "⚠️"
		"perform_ritual":  return "🙏"
		"gather_resource": return "🌿"
		_:                 return "💬"
