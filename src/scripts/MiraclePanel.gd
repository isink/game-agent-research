## MiraclePanel.gd
## Player interface for selecting and launching miracles.
## Each miracle has a faith cost and cooldown.

class_name MiraclePanel
extends PanelContainer

signal miracle_requested(miracle_type: String)

const MIRACLE_DATA := {
	"rain":      {"label": "降雨",   "emoji": "🌧",  "cost": 8,   "desc": "无云的天空骤降大雨"},
	"lightning": {"label": "雷击",   "emoji": "⚡",  "cost": 12,  "desc": "闪电劈中村中心的古橡树"},
	"harvest":   {"label": "丰收",   "emoji": "🌾",  "cost": 18,  "desc": "一夜之间庄稼长了三倍"},
	"plague":    {"label": "瘟疫",   "emoji": "🦠",  "cost": 22,  "desc": "三名村民同时染上怪病"},
	"fire":      {"label": "圣火",   "emoji": "🔥",  "cost": 18,  "desc": "空地上燃起完美圆形的火焰"},
	"eclipse":   {"label": "日蚀",   "emoji": "🌑",  "cost": 28,  "desc": "正午太阳突然消失"},
}

const COOLDOWN_SECONDS := 12.0

var _cooldowns: Dictionary = {}
var _current_faith: float  = 0.0   # updated by Main.gd

@onready var button_container: VBoxContainer = $MarginContainer/VBoxContainer/Buttons
@onready var title_label: Label = $MarginContainer/VBoxContainer/Title
@onready var desc_label: Label  = $MarginContainer/VBoxContainer/Description


func _ready() -> void:
	title_label.text = "⚡ 神迹"
	desc_label.text  = "选择施放的神迹"
	_build_buttons()


func _process(delta: float) -> void:
	for miracle_type in _cooldowns:
		if _cooldowns[miracle_type] > 0.0:
			_cooldowns[miracle_type] = maxf(0.0, _cooldowns[miracle_type] - delta)
	_refresh_button_states()


## Called by Main each tick with the current faith value.
func set_faith(value: float) -> void:
	_current_faith = value


func get_miracle_cost(miracle_type: String) -> int:
	return MIRACLE_DATA.get(miracle_type, {}).get("cost", 10)


# ── Internal ───────────────────────────────────────────────────────────────────

func _build_buttons() -> void:
	for miracle_type in MIRACLE_DATA:
		var data: Dictionary = MIRACLE_DATA[miracle_type]
		var btn := Button.new()
		btn.name = miracle_type
		btn.text = "%s %s  [%d✝]" % [data["emoji"], data["label"], data["cost"]]
		btn.tooltip_text = data["desc"]
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.custom_minimum_size = Vector2(0, 36)
		btn.pressed.connect(_on_miracle_pressed.bind(miracle_type))
		button_container.add_child(btn)
		_cooldowns[miracle_type] = 0.0


func _on_miracle_pressed(miracle_type: String) -> void:
	var cost: int = MIRACLE_DATA[miracle_type]["cost"]
	if _cooldowns.get(miracle_type, 0.0) > 0:
		return
	if _current_faith < cost:
		desc_label.text = "信仰不足！需要 %d✝" % cost
		return
	desc_label.text = MIRACLE_DATA[miracle_type]["desc"]
	_cooldowns[miracle_type] = COOLDOWN_SECONDS
	miracle_requested.emit(miracle_type)


func _refresh_button_states() -> void:
	for child in button_container.get_children():
		var miracle_type: String = child.name
		var cd: float = _cooldowns.get(miracle_type, 0.0)
		var data: Dictionary = MIRACLE_DATA.get(miracle_type, {})
		var cost: int = data.get("cost", 10)

		if cd > 0:
			child.disabled = true
			child.text = "⏳ %.0fs" % cd
		elif _current_faith < cost:
			child.disabled = true
			child.text = "%s %s  [%d✝] ✗" % [data.get("emoji", ""), data.get("label", ""), cost]
		else:
			child.disabled = false
			child.text = "%s %s  [%d✝]" % [data.get("emoji", ""), data.get("label", ""), cost]
