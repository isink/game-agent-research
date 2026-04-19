## Villager.gd
## Visual representation of one LLM agent in the village.
##
## Features:
##   - Procedural body (circle head + body) colored by occupation
##   - Smooth random wandering on grid
##   - Speech bubble with fade
##   - Belief/action indicators
##   - Witness highlight flash

class_name Villager
extends Node2D

const TILE_SIZE := 64
const WANDER_INTERVAL_MIN := 3.0
const WANDER_INTERVAL_MAX := 7.0
const MOVE_DURATION := 0.6

@onready var name_label:       Label          = $NameLabel
@onready var speech_bubble:    PanelContainer = $SpeechBubble
@onready var speech_label:     Label          = $SpeechBubble/SpeechLabel
@onready var action_label:     Label          = $ActionLabel
@onready var belief_indicator:  Label         = $BeliefIndicator
@onready var drift_bar:        ProgressBar    = $DriftBar

var agent_id:    String
var agent_name:  String
var occupation:  String
var personality: Dictionary = {}
var beliefs:     Array[String] = []
var avg_drift:   float = 0.0

# Grid position (integer cells)
var grid_pos: Vector2i = Vector2i.ZERO

# Visual
var _body_color: Color = Color(0.55, 0.55, 0.55)
var _highlight:  Color = Color.WHITE
var _bob_phase:  float = 0.0   # idle bobbing animation

# Speech
const SPEECH_DURATION := 5.0
var _speech_timer:   float = 0.0
var _showing_speech:  bool = false
var _speech_fade_tween: Tween

# Wander
var _wander_timer: float = 0.0

# Action type icons
const ACTION_ICONS := {
	"share_rumor":     "💬",
	"warn":            "⚠️",
	"perform_ritual":  "🙏",
	"gather_resource": "🌿",
	"idle":            "",
}


func _ready() -> void:
	speech_bubble.visible    = false
	belief_indicator.visible = false
	action_label.visible     = false
	_wander_timer = randf_range(1.0, WANDER_INTERVAL_MAX)
	speech_bubble.modulate.a = 1.0


func _process(delta: float) -> void:
	# Idle bob animation
	_bob_phase += delta * 2.5
	queue_redraw()

	# Speech fade
	if _showing_speech:
		_speech_timer -= delta
		if _speech_timer <= 1.0 and _speech_timer > 0.0:
			speech_bubble.modulate.a = _speech_timer
		elif _speech_timer <= 0.0:
			speech_bubble.visible = false
			_showing_speech = false

	# Random wander
	_wander_timer -= delta
	if _wander_timer <= 0.0:
		_wander_timer = randf_range(WANDER_INTERVAL_MIN, WANDER_INTERVAL_MAX)
		_wander_step()


func _draw() -> void:
	var lit: Color = _body_color * _highlight
	var bob: float = sin(_bob_phase) * 1.5

	# Shadow
	draw_circle(Vector2(2.0, 3.0 + bob), 16.0, Color(0.0, 0.0, 0.0, 0.3))
	# Body
	draw_circle(Vector2(0.0, bob), 16.0, lit)
	# Body outline
	draw_arc(Vector2(0.0, bob), 16.0, 0.0, TAU, 28, lit.darkened(0.3), 1.5)
	# Head
	draw_circle(Vector2(0.0, -12.0 + bob), 7.0, lit.lightened(0.3))
	# Eyes (tiny dots)
	var eye_y: float = -13.0 + bob
	draw_circle(Vector2(-2.5, eye_y), 1.2, Color(0.15, 0.15, 0.15))
	draw_circle(Vector2(2.5, eye_y), 1.2, Color(0.15, 0.15, 0.15))


# ── Public API ────────────────────────────────────────────────────────────────

func setup(data: Dictionary) -> void:
	agent_id   = data.get("agent_id", "")
	agent_name = data.get("name", "?")
	occupation = data.get("occupation", "")
	personality = data.get("personality", {})

	name_label.text = agent_name

	var pos_arr: Array = data.get("position", [0, 0])
	grid_pos = Vector2i(int(pos_arr[0]), int(pos_arr[1]))
	position = Vector2(grid_pos.x * TILE_SIZE, grid_pos.y * TILE_SIZE)

	_set_color_from_occupation(occupation)


func update_from_state(data: Dictionary) -> void:
	# Speech bubble
	var speech: String = data.get("last_speech", "")
	if speech != "":
		show_speech(speech)

	# Action type icon (Hermes)
	var action: String = data.get("last_action_type", "share_rumor")
	var icon: String = ACTION_ICONS.get(action, "💬")
	if icon != "":
		action_label.text    = icon
		action_label.visible = true
	else:
		action_label.visible = false

	# Beliefs
	var new_beliefs: Array = data.get("belief_summary", [])
	beliefs = []
	for b in new_beliefs:
		beliefs.append(str(b))
	if beliefs.size() > 0:
		belief_indicator.visible      = true
		belief_indicator.tooltip_text  = beliefs[0]
	else:
		belief_indicator.visible = false

	# Drift bar
	var research: Dictionary = data.get("research", {})
	avg_drift       = research.get("avg_semantic_drift", 0.0)
	drift_bar.value = avg_drift * 100.0


func show_speech(text: String) -> void:
	var display: String = text.left(80) + ("…" if text.length() > 80 else "")
	speech_label.text          = display
	speech_bubble.visible      = true
	speech_bubble.modulate.a   = 1.0
	_speech_timer              = SPEECH_DURATION
	_showing_speech            = true


func highlight_as_witness() -> void:
	"""Flash yellow when this agent witnesses a miracle."""
	var tw := create_tween()
	tw.tween_method(
		func(c: Color) -> void: _highlight = c; queue_redraw(),
		Color.WHITE, Color(1.3, 1.2, 0.4), 0.12,
	)
	tw.tween_method(
		func(c: Color) -> void: _highlight = c; queue_redraw(),
		Color(1.3, 1.2, 0.4), Color.WHITE, 0.7,
	)


func get_belief_count() -> int:
	return beliefs.size()


# ── Movement ──────────────────────────────────────────────────────────────────

func _wander_step() -> void:
	"""Move to a random adjacent grid cell (clamped to village bounds)."""
	var dirs := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	var dir: Vector2i = dirs[randi() % dirs.size()]
	var new_pos: Vector2i = grid_pos + dir

	# Clamp to village grid (0..11, 0..9)
	new_pos.x = clampi(new_pos.x, 0, 11)
	new_pos.y = clampi(new_pos.y, 0, 9)

	if new_pos == grid_pos:
		return

	grid_pos = new_pos
	var target := Vector2(grid_pos.x * TILE_SIZE, grid_pos.y * TILE_SIZE)

	var tw := create_tween()
	tw.set_ease(Tween.EASE_OUT)
	tw.set_trans(Tween.TRANS_CUBIC)
	tw.tween_property(self, "position", target, MOVE_DURATION)


# ── Internal ──────────────────────────────────────────────────────────────────

func _set_color_from_occupation(occ: String) -> void:
	match occ.to_lower():
		"blacksmith":          _body_color = Color(0.42, 0.42, 0.62)
		"herbalist":           _body_color = Color(0.28, 0.68, 0.32)
		"village elder":       _body_color = Color(0.82, 0.72, 0.22)
		"hunter":              _body_color = Color(0.52, 0.32, 0.14)
		"innkeeper":           _body_color = Color(0.85, 0.54, 0.24)
		"weaver":              _body_color = Color(0.68, 0.38, 0.72)
		"shepherd":            _body_color = Color(0.62, 0.82, 0.52)
		"farmer's daughter":   _body_color = Color(0.88, 0.68, 0.48)
		_:                     _body_color = Color(0.55, 0.55, 0.55)
	queue_redraw()
