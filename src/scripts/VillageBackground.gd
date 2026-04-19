## VillageBackground.gd
## Procedural village floor: grass grid + decorations (houses, trees, paths).
## No textures needed — everything drawn via CanvasItem.

extends Node2D

const TILE_SIZE := 64
const GRID_W    := 12
const GRID_H    := 10

# Grass palette
const GRASS_A := Color(0.15, 0.25, 0.12)
const GRASS_B := Color(0.18, 0.28, 0.14)
const GRASS_C := Color(0.13, 0.23, 0.10)
const GRID_LINE := Color(0.0, 0.0, 0.0, 0.08)

# Decorations (grid coords)
const HOUSES := [
	Vector2i(1, 1), Vector2i(2, 1),     # top-left cluster
	Vector2i(10, 1), Vector2i(10, 2),   # top-right
	Vector2i(1, 7), Vector2i(2, 8),     # bottom-left
	Vector2i(9, 7), Vector2i(10, 8),    # bottom-right
]
const TREES := [
	Vector2i(0, 4), Vector2i(0, 5),
	Vector2i(11, 3), Vector2i(11, 6),
	Vector2i(5, 0), Vector2i(7, 0),
	Vector2i(5, 9), Vector2i(8, 9),
	Vector2i(3, 5), Vector2i(8, 4),
]
const OAK_POS := Vector2i(5, 4)   # central ancient oak
const PATH_TILES := [
	# Horizontal road through village center
	Vector2i(0, 4), Vector2i(1, 4), Vector2i(2, 4), Vector2i(3, 4),
	Vector2i(4, 4), Vector2i(5, 4), Vector2i(6, 4), Vector2i(7, 4),
	Vector2i(8, 4), Vector2i(9, 4), Vector2i(10, 4), Vector2i(11, 4),
	# Vertical crossroad
	Vector2i(5, 0), Vector2i(5, 1), Vector2i(5, 2), Vector2i(5, 3),
	Vector2i(5, 5), Vector2i(5, 6), Vector2i(5, 7), Vector2i(5, 8), Vector2i(5, 9),
]

# Miracle flash
var _miracle_pos:  Vector2i = Vector2i(-1, -1)
var _miracle_glow: float    = 0.0


func _process(delta: float) -> void:
	if _miracle_glow > 0.0:
		_miracle_glow = maxf(0.0, _miracle_glow - delta * 0.35)
		queue_redraw()


func _draw() -> void:
	var palette := [GRASS_A, GRASS_B, GRASS_C]
	var path_color := Color(0.28, 0.22, 0.14)

	for x in range(GRID_W):
		for y in range(GRID_H):
			var rect := Rect2(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
			var cell := Vector2i(x, y)

			# Base color
			var base: Color
			if cell in PATH_TILES:
				base = path_color
			else:
				base = palette[(x * 3 + y * 7 + x * y) % palette.size()]

			# Miracle glow
			if _miracle_glow > 0.0 and cell == _miracle_pos:
				base = base.lerp(Color(1.0, 0.9, 0.3, 1.0), _miracle_glow * 0.6)

			draw_rect(rect, base)
			draw_rect(rect, GRID_LINE, false, 1.0)

	# Draw houses
	for h in HOUSES:
		_draw_house(h)

	# Draw trees
	for t in TREES:
		_draw_tree(t)

	# Draw ancient oak (larger, central)
	_draw_oak(OAK_POS)


func flash_miracle(grid_pos: Vector2i) -> void:
	_miracle_pos  = grid_pos
	_miracle_glow = 1.0
	queue_redraw()


# ── Drawing helpers ────────────────────────────────────────────────────────────

func _draw_house(cell: Vector2i) -> void:
	var cx: float = cell.x * TILE_SIZE + TILE_SIZE * 0.5
	var cy: float = cell.y * TILE_SIZE + TILE_SIZE * 0.5

	# Walls
	var wall_rect := Rect2(cx - 20, cy - 12, 40, 28)
	draw_rect(wall_rect, Color(0.55, 0.40, 0.25))
	draw_rect(wall_rect, Color(0.35, 0.25, 0.15), false, 1.5)

	# Roof (triangle)
	var roof := PackedVector2Array([
		Vector2(cx - 24, cy - 12),
		Vector2(cx, cy - 30),
		Vector2(cx + 24, cy - 12),
	])
	draw_colored_polygon(roof, Color(0.6, 0.2, 0.15))

	# Door
	draw_rect(Rect2(cx - 5, cy + 2, 10, 14), Color(0.3, 0.2, 0.1))

	# Window
	draw_rect(Rect2(cx + 10, cy - 6, 8, 8), Color(0.85, 0.8, 0.4, 0.7))


func _draw_tree(cell: Vector2i) -> void:
	var cx: float = cell.x * TILE_SIZE + TILE_SIZE * 0.5
	var cy: float = cell.y * TILE_SIZE + TILE_SIZE * 0.5

	# Trunk
	draw_rect(Rect2(cx - 3, cy - 2, 6, 18), Color(0.4, 0.25, 0.1))
	# Canopy
	draw_circle(Vector2(cx, cy - 10), 13.0, Color(0.15, 0.45, 0.12))
	draw_circle(Vector2(cx - 6, cy - 5), 9.0, Color(0.18, 0.40, 0.14))
	draw_circle(Vector2(cx + 6, cy - 5), 9.0, Color(0.12, 0.42, 0.10))


func _draw_oak(cell: Vector2i) -> void:
	"""The ancient oak — village center and miracle focal point."""
	var cx: float = cell.x * TILE_SIZE + TILE_SIZE * 0.5
	var cy: float = cell.y * TILE_SIZE + TILE_SIZE * 0.5

	# Thick trunk
	draw_rect(Rect2(cx - 6, cy - 4, 12, 24), Color(0.38, 0.22, 0.08))
	# Large canopy
	draw_circle(Vector2(cx, cy - 14), 20.0, Color(0.12, 0.40, 0.10))
	draw_circle(Vector2(cx - 10, cy - 6), 14.0, Color(0.14, 0.38, 0.12))
	draw_circle(Vector2(cx + 10, cy - 6), 14.0, Color(0.10, 0.36, 0.08))
	draw_circle(Vector2(cx, cy - 22), 12.0, Color(0.16, 0.42, 0.14))

	# Glow ring when miracle hits nearby
	if _miracle_glow > 0.0:
		var glow_alpha: float = _miracle_glow * 0.4
		draw_arc(Vector2(cx, cy - 10), 28.0, 0.0, TAU, 32,
			Color(1.0, 0.9, 0.3, glow_alpha), 3.0)
