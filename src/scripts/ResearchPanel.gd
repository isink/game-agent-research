## ResearchPanel.gd
## Real-time research metrics panel — the "god's eye" view for researchers.
## Toggle with Tab.
##
## Displays:
##   - Semantic drift (avg + per-hop bar chart)
##   - Social narratives
##   - Agent beliefs (L4)
##   - Learned rituals / procedural memory (Hermes L2)
##   - Memory tier breakdown (episodic / semantic / procedural)

class_name ResearchPanel
extends PanelContainer

signal export_requested

@onready var tick_label:      Label          = $Margin/VBox/TickLabel
@onready var drift_label:     Label          = $Margin/VBox/DriftLabel
@onready var hop_chart:       VBoxContainer  = $Margin/VBox/HopChart
@onready var narratives_list: ItemList       = $Margin/VBox/NarrativesList
@onready var beliefs_text:    RichTextLabel  = $Margin/VBox/BeliefsText
@onready var procedures_text: RichTextLabel  = $Margin/VBox/ProceduresText
@onready var tiers_text:      RichTextLabel  = $Margin/VBox/TiersText
@onready var export_btn:      Button         = $Margin/VBox/ExportBtn


func _ready() -> void:
	export_btn.pressed.connect(func() -> void: export_requested.emit())
	_build_hop_chart()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_TAB:
		visible = not visible
		get_viewport().set_input_as_handled()


# ── Update from tick data ──────────────────────────────────────────────────────

func update_from_tick(data: Dictionary) -> void:
	var metrics:    Dictionary = data.get("research_metrics", {})
	var tick:       int        = data.get("tick", 0)
	var agents:     Array      = data.get("agent_states", [])
	var narratives: Array      = data.get("social_narratives", [])

	tick_label.text = "Tick: %d" % tick

	# Average semantic drift
	var drift: float = metrics.get("avg_semantic_drift", 0.0)
	drift_label.text = "Avg Drift: %.4f  [%s]" % [drift, _drift_bar(drift)]

	# Per-hop drift bars
	_update_hop_chart(metrics.get("drift_by_hop", {}))

	# Social narratives
	narratives_list.clear()
	for n in narratives:
		var label := "[%d×] %s" % [
			n.get("reinforcement_count", n.get("reinforcement", 1)),
			str(n.get("social_version", n.get("social", ""))).left(58),
		]
		narratives_list.add_item(label)

	# Agent beliefs (L4)
	var belief_lines := ""
	for a in agents:
		var aname: String = a.get("name", "?")
		var b_list: Array = a.get("belief_summary", [])
		if b_list.size() > 0:
			belief_lines += "[b]%s:[/b] %s\n" % [aname, str(b_list[0]).left(55)]
	beliefs_text.text = belief_lines if belief_lines != "" else "[i]No beliefs yet[/i]"

	# Procedural memory — Hermes
	var proc_lines := ""
	for a in agents:
		var aname: String  = a.get("name", "?")
		var procs: Array   = a.get("procedures", [])
		if procs.size() > 0:
			proc_lines += "[b]%s:[/b] %s\n" % [aname, str(procs[0]).left(55)]
	procedures_text.text = proc_lines if proc_lines != "" else "[i]No rituals learned yet[/i]"

	# Memory tier breakdown
	var tier_lines := ""
	for a in agents:
		var aname: String    = a.get("name", "?")
		var research: Dictionary = a.get("research", {})
		var tiers: Dictionary    = research.get("memory_tiers", {})
		if tiers:
			tier_lines += "[b]%s[/b] E:%d S:%d P:%d\n" % [
				aname.left(5),
				tiers.get("episodic", 0),
				tiers.get("semantic", 0),
				tiers.get("procedural", 0),
			]
	tiers_text.text = tier_lines if tier_lines != "" else ""


# ── Internal ───────────────────────────────────────────────────────────────────

func _build_hop_chart() -> void:
	for i in range(1, 6):
		var row := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = "Hop%d: " % i
		lbl.custom_minimum_size = Vector2(52, 0)
		lbl.add_theme_font_size_override("font_size", 11)
		var bar := ProgressBar.new()
		bar.max_value = 1.0
		bar.value     = 0.0
		bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar.name      = "HopBar%d" % i
		row.add_child(lbl)
		row.add_child(bar)
		hop_chart.add_child(row)


func _update_hop_chart(hop_drift: Dictionary) -> void:
	for i in range(1, 6):
		var bar: ProgressBar = hop_chart.find_child("HopBar%d" % i, true, false)
		if bar:
			bar.value = hop_drift.get(str(i), hop_drift.get(i, 0.0))


static func _drift_bar(value: float) -> String:
	var filled := clampi(int(value * 20), 0, 20)
	return "█".repeat(filled) + "░".repeat(20 - filled)
