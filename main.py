"""FourWay TD — Kivy / Android build entrypoint.

Ports the desktop combat loop: Cross / Lance / Pulse / Arc towers with their
bullet behaviors, merge/tier rules, four-front pathfinding, and splitter enemies.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, Triangle
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from pathfinding import astar_pathfinding

WIN_SIZE = 600
GRIDS_SIZE = 200
EDGES = 5
GRIDS_INTERVAL = GRIDS_SIZE / EDGES
ROAD_LENGTH = (WIN_SIZE - GRIDS_SIZE) / 2
TRAY_H = 78
MAX_TIER = 4
SIDES = ("N", "E", "S", "W")
# Facing order matches desktop Direction offsets: N, E, S, W
FACINGS = ("N", "E", "S", "W")
FACING_VEC = {
    "N": (0.0, 1.0),
    "E": (1.0, 0.0),
    "S": (0.0, -1.0),
    "W": (-1.0, 0.0),
}
# Desktop TestTower2.tri — offsets from facing by tier
LANCE_TRI = {1: [0], 2: [0, 2], 3: [-1, 0, 1], 4: [-1, 0, 1, 2]}


@dataclass(frozen=True)
class TowerKind:
    key: str
    name: str
    price: int
    color: tuple[float, float, float]
    mergeable: bool
    shape: str  # circle | triangle | hex | dark
    base_interval: float
    note: str = ""


TOWER_KINDS = {
    # Desktop TestTower — cardinal minigun, never merges
    "cross": TowerKind(
        "cross", "Cross", 10, (1.0, 0.9, 0.2), False, "circle", 0.8, "4-way shots"
    ),
    # Desktop TestTower2 — mergeable directional lasers; tap to rotate
    "lance": TowerKind(
        "lance", "Lance", 5, (1.0, 0.84, 0.15), True, "triangle", 1.5, "lasers · tap rotate"
    ),
    # Desktop TestTower3 — shockwave + freeze; no merge on desktop
    "pulse": TowerKind(
        "pulse", "Pulse", 10, (0.25, 0.45, 0.95), False, "hex", 1.9, "shock + freeze"
    ),
    # Desktop TestTower4 — mergeable chain lightning
    "arc": TowerKind(
        "arc", "Arc", 10, (0.12, 0.12, 0.14), True, "dark", 0.5, "chain lightning"
    ),
}

TOWER_ORDER = ("cross", "lance", "pulse", "arc")


def facing_offset(facing: str, offset: int) -> str:
    idx = FACINGS.index(facing)
    return FACINGS[(idx + offset) % 4]


def start_for(side: str, lane: int) -> tuple[int, int]:
    if side == "N":
        return (0, lane)
    if side == "S":
        return (EDGES - 1, lane)
    if side == "W":
        return (lane, 0)
    return (lane, EDGES - 1)


def goal_for(side: str, lane: int, nav_map: list[list[bool]]) -> tuple[int, int] | None:
    if side == "N":
        edge = [(EDGES - 1, c) for c in range(EDGES)]
        preferred = (EDGES - 1, lane)
    elif side == "S":
        edge = [(0, c) for c in range(EDGES)]
        preferred = (0, lane)
    elif side == "W":
        edge = [(r, EDGES - 1) for r in range(EDGES)]
        preferred = (lane, EDGES - 1)
    else:
        edge = [(r, 0) for r in range(EDGES)]
        preferred = (lane, 0)

    if nav_map[preferred[0]][preferred[1]]:
        return preferred
    for cell in edge:
        if nav_map[cell[0]][cell[1]]:
            return cell
    return None


def reached_exit(enemy: dict) -> bool:
    if not enemy.get("path"):
        return False
    if enemy["path_index"] != len(enemy["path"]) - 1:
        return False
    row, col = enemy["row"], enemy["col"]
    side = enemy["side"]
    if side == "N":
        return row == EDGES - 1
    if side == "S":
        return row == 0
    if side == "W":
        return col == EDGES - 1
    return col == 0


def cell_center(grid_top_left: tuple[float, float], row: float, col: float) -> tuple[float, float]:
    x = grid_top_left[0] + col * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
    y = grid_top_left[1] + row * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
    return x, y


def gauss01(x: float) -> float:
    """Approximate scipy.stats.norm.pdf(x, 0, 1) without scipy (APK-safe)."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass
class Effect:
    kind: str
    life: float
    max_life: float
    x: float = 0.0
    y: float = 0.0
    data: dict = field(default_factory=dict)


class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (WIN_SIZE, WIN_SIZE)
        self.grid_top_left = (ROAD_LENGTH, ROAD_LENGTH)
        self.selected_cell = None
        self.selected_kind = "cross"
        self.towers: dict[tuple[int, int], dict] = {}
        self.enemies: list[dict] = []
        self.bullets: list[dict] = []
        self.effects: list[Effect] = []
        self.spawn_timer = 0.0
        self.split_timer = 0.0
        self.hp = 20
        self.gold = 100
        self.show_intro = True
        self.wave = 0

        self.hp_label = Label(
            text=f"HP: {self.hp}",
            size_hint=(None, None),
            pos=(10, WIN_SIZE - 30),
            color=(0.9, 0.2, 0.2, 1),
            font_size=18,
        )
        self.gold_label = Label(
            text=f"Gold: {self.gold}",
            size_hint=(None, None),
            pos=(110, WIN_SIZE - 30),
            color=(1, 0.84, 0, 1),
            font_size=18,
        )
        self.title_label = Label(
            text="FOURWAY TD",
            size_hint=(None, None),
            size=(WIN_SIZE, 36),
            pos=(0, WIN_SIZE - 68),
            color=(0.08, 0.14, 0.2, 1),
            font_size=20,
            bold=True,
        )
        self.hint_label = Label(
            text="Cross · Lance · Pulse · Arc — merge Lance/Arc · tap Lance to rotate",
            size_hint=(None, None),
            size=(WIN_SIZE, 26),
            pos=(0, TRAY_H + 6),
            color=(0.08, 0.14, 0.2, 0.9),
            font_size=12,
        )
        self.tier_labels: dict[tuple[int, int], Label] = {}
        self.add_widget(self.hp_label)
        self.add_widget(self.gold_label)
        self.add_widget(self.title_label)
        self.add_widget(self.hint_label)
        self.draw_grid()

    def tray_rects(self) -> dict[str, tuple[float, float, float, float]]:
        keys = list(TOWER_ORDER)
        pad = 8
        slot_w = (WIN_SIZE - pad * (len(keys) + 1)) / len(keys)
        rects = {}
        for i, key in enumerate(keys):
            x = pad + i * (slot_w + pad)
            y = 8
            rects[key] = (x, y, slot_w, TRAY_H - 14)
        return rects

    def sync_tier_labels(self):
        live = set(self.towers)
        for cell, label in list(self.tier_labels.items()):
            if cell not in live:
                self.remove_widget(label)
                del self.tier_labels[cell]
        for (row, col), tower in self.towers.items():
            kind = TOWER_KINDS[tower["kind"]]
            if not kind.mergeable:
                if (row, col) in self.tier_labels:
                    self.remove_widget(self.tier_labels[(row, col)])
                    del self.tier_labels[(row, col)]
                continue
            x, y = cell_center(self.grid_top_left, row, col)
            text = str(tower["tier"])
            color = (0.95, 0.95, 0.95, 1) if kind.key == "arc" else (0.05, 0.08, 0.12, 1)
            if (row, col) not in self.tier_labels:
                label = Label(
                    text=text,
                    size_hint=(None, None),
                    size=(GRIDS_INTERVAL, GRIDS_INTERVAL),
                    pos=(x - GRIDS_INTERVAL / 2, y - GRIDS_INTERVAL / 2),
                    color=color,
                    font_size=16,
                    bold=True,
                )
                self.tier_labels[(row, col)] = label
                self.add_widget(label)
            else:
                label = self.tier_labels[(row, col)]
                label.text = text
                label.color = color
                label.pos = (x - GRIDS_INTERVAL / 2, y - GRIDS_INTERVAL / 2)

    def draw_hex(self, cx: float, cy: float, r: float):
        pts = []
        for i in range(6):
            ang = math.pi / 6 + i * math.pi / 3
            pts.extend([cx + r * math.cos(ang), cy + r * math.sin(ang)])
        # Approximate hex with triangle fan via two triangles + middle
        Triangle(points=[pts[0], pts[1], pts[2], pts[3], pts[4], pts[5]])
        Triangle(points=[pts[0], pts[1], pts[4], pts[5], pts[6], pts[7]])
        Triangle(points=[pts[0], pts[1], pts[6], pts[7], pts[8], pts[9]])
        Triangle(points=[pts[0], pts[1], pts[8], pts[9], pts[10], pts[11]])

    def draw_grid(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.12, 0.18, 0.26, 0.3)
            for i in range(EDGES):
                x = self.grid_top_left[0] + i * GRIDS_INTERVAL
                Rectangle(pos=(x + 4, TRAY_H), size=(GRIDS_INTERVAL - 8, max(8, ROAD_LENGTH - 8)))
                Rectangle(
                    pos=(x + 4, self.grid_top_left[1] + GRIDS_SIZE),
                    size=(GRIDS_INTERVAL - 8, max(8, ROAD_LENGTH - 8)),
                )
            for i in range(EDGES):
                y = self.grid_top_left[1] + i * GRIDS_INTERVAL
                Rectangle(pos=(0, y + 4), size=(ROAD_LENGTH, GRIDS_INTERVAL - 8))
                Rectangle(
                    pos=(self.grid_top_left[0] + GRIDS_SIZE, y + 4),
                    size=(ROAD_LENGTH, GRIDS_INTERVAL - 8),
                )

            Color(0.68, 0.83, 0.64, 1)
            Rectangle(pos=self.grid_top_left, size=(GRIDS_SIZE, GRIDS_SIZE))

            Color(0.08, 0.14, 0.2, 1)
            for i in range(EDGES + 1):
                Line(
                    points=[
                        self.grid_top_left[0],
                        self.grid_top_left[1] + i * GRIDS_INTERVAL,
                        self.grid_top_left[0] + GRIDS_SIZE,
                        self.grid_top_left[1] + i * GRIDS_INTERVAL,
                    ],
                    width=1,
                )
                Line(
                    points=[
                        self.grid_top_left[0] + i * GRIDS_INTERVAL,
                        self.grid_top_left[1],
                        self.grid_top_left[0] + i * GRIDS_INTERVAL,
                        self.grid_top_left[1] + GRIDS_SIZE,
                    ],
                    width=1,
                )

            for (row, col), tower in self.towers.items():
                kind = TOWER_KINDS[tower["kind"]]
                Color(*kind.color, 1)
                pad = GRIDS_INTERVAL * 0.14
                x = self.grid_top_left[0] + col * GRIDS_INTERVAL + pad
                y = self.grid_top_left[1] + row * GRIDS_INTERVAL + pad
                size = GRIDS_INTERVAL - pad * 2
                cx, cy = x + size / 2, y + size / 2
                if kind.shape == "triangle":
                    # Point toward facing
                    fx, fy = FACING_VEC[tower.get("facing", "N")]
                    # Kivy y increases up; facing N is +y in our FACING_VEC
                    tip = (cx + fx * size * 0.45, cy + fy * size * 0.45)
                    left = (cx - fy * size * 0.35 - fx * size * 0.15, cy + fx * size * 0.35 - fy * size * 0.15)
                    right = (cx + fy * size * 0.35 - fx * size * 0.15, cy - fx * size * 0.35 - fy * size * 0.15)
                    Triangle(points=[tip[0], tip[1], left[0], left[1], right[0], right[1]])
                    # Extra tips for higher tiers
                    for off in LANCE_TRI[tower["tier"]][1:]:
                        f2 = facing_offset(tower.get("facing", "N"), off)
                        fx2, fy2 = FACING_VEC[f2]
                        tip2 = (cx + fx2 * size * 0.4, cy + fy2 * size * 0.4)
                        Ellipse(pos=(tip2[0] - 3, tip2[1] - 3), size=(6, 6))
                elif kind.shape == "hex":
                    self.draw_hex(cx, cy, size * 0.48)
                elif kind.shape == "dark":
                    Ellipse(pos=(x, y), size=(size, size))
                else:
                    Ellipse(pos=(x, y), size=(size, size))

            for enemy in self.enemies:
                pos = self.enemy_world_pos(enemy)
                if pos is None:
                    continue
                x, y = pos
                hp_ratio = max(0.15, enemy["hp"] / enemy["max_hp"])
                if enemy.get("splitter"):
                    Color(0.1, 0.85, 0.9, 1)
                else:
                    Color(0.85, 0.15 + 0.2 * (1 - hp_ratio), 0.15, 1)
                r = GRIDS_INTERVAL * (0.22 if enemy.get("minor") else 0.28)
                Ellipse(pos=(x - r, y - r), size=(r * 2, r * 2))

            # Projectiles
            for bullet in self.bullets:
                if bullet["kind"] == "cross":
                    Color(0.05, 0.05, 0.05, 0.95)
                    Ellipse(pos=(bullet["x"] - 2.5, bullet["y"] - 2.5), size=(5, 5))
                elif bullet["kind"] == "arc_bolt":
                    Color(0.45, 0.75, 1.0, 0.95)
                    Ellipse(pos=(bullet["x"] - 3, bullet["y"] - 3), size=(6, 6))

            # Beams / pulses / chains
            for fx in self.effects:
                t = 1.0 - fx.life / fx.max_life
                if fx.kind == "laser":
                    # Pulsing width like desktop norm.pdf animation
                    x = t * 10 - 5
                    y = gauss01(x)
                    width = max(4.0, GRIDS_INTERVAL * 1.1 * y)
                    Color(0.7, 1.0, 1.0, min(0.85, 0.3 + y))
                    facing = fx.data["facing"]
                    x0, y0 = fx.x, fx.y
                    if facing in ("N", "S"):
                        Rectangle(
                            pos=(x0 - width / 2, 0 if facing == "S" else y0),
                            size=(width, y0 if facing == "S" else WIN_SIZE - y0),
                        )
                    else:
                        Rectangle(
                            pos=(0 if facing == "W" else x0, y0 - width / 2),
                            size=(x0 if facing == "W" else WIN_SIZE - x0, width),
                        )
                elif fx.kind == "pulse":
                    progress = t
                    r = fx.data["radius"] * progress
                    Color(0.25, 0.45, 0.95, max(0.15, 0.7 - progress * 0.6))
                    Line(
                        circle=(fx.x, fx.y, max(2.0, r)),
                        width=max(1.0, 6 * (1 - progress)),
                    )
                elif fx.kind == "chain":
                    Color(0.55, 0.8, 1.0, max(0.2, 1.0 - t))
                    Line(
                        points=[fx.data["x0"], fx.data["y0"], fx.data["x1"], fx.data["y1"]],
                        width=2.5,
                    )

            # Tray
            Color(0.08, 0.12, 0.18, 0.94)
            Rectangle(pos=(0, 0), size=(WIN_SIZE, TRAY_H))
            for key, (x, y, w, h) in self.tray_rects().items():
                kind = TOWER_KINDS[key]
                selected = key == self.selected_kind
                Color(*(kind.color if selected else (0.28, 0.32, 0.38)), 1)
                Rectangle(pos=(x, y), size=(w, h))
                if selected:
                    Color(0.95, 0.96, 0.9, 1)
                    Line(rectangle=(x, y, w, h), width=1.5)

            if self.selected_cell:
                r, c = self.selected_cell
                Color(1, 1, 0, 0.22)
                Rectangle(
                    pos=(
                        self.grid_top_left[0] + c * GRIDS_INTERVAL,
                        self.grid_top_left[1] + r * GRIDS_INTERVAL,
                    ),
                    size=(GRIDS_INTERVAL, GRIDS_INTERVAL),
                )

            if self.show_intro:
                Color(0.06, 0.1, 0.16, 0.75)
                Rectangle(pos=(0, 0), size=(WIN_SIZE, WIN_SIZE))
                Color(0.95, 0.96, 0.92, 1)
                Rectangle(pos=(40, WIN_SIZE / 2 - 90), size=(WIN_SIZE - 80, 180))

        self.hp_label.text = f"HP: {self.hp}"
        self.gold_label.text = f"Gold: {self.gold}"
        if self.show_intro:
            self.title_label.text = "FOURWAY TD"
            self.hint_label.text = "Tap — Cross · Lance · Pulse · Arc hold the crossroads"
            self.title_label.pos = (0, WIN_SIZE / 2 + 10)
            self.hint_label.pos = (0, WIN_SIZE / 2 - 30)
        else:
            self.title_label.pos = (0, WIN_SIZE - 68)
            self.hint_label.pos = (0, TRAY_H + 6)
            kind = TOWER_KINDS[self.selected_kind]
            merge = f"merge→T{MAX_TIER}" if kind.mergeable else "no merge"
            self.hint_label.text = f"{kind.name} · {kind.price}g · {kind.note} · {merge}"
        self.sync_tier_labels()

    def build_navigation_map(self):
        nav_map = [[True for _ in range(EDGES)] for _ in range(EDGES)]
        for row, col in self.towers:
            nav_map[row][col] = False
        return nav_map

    def recalculate_enemy_paths(self):
        nav_map = self.build_navigation_map()
        for enemy in self.enemies:
            start = (
                enemy["path"][enemy["path_index"]]
                if enemy.get("path")
                else (enemy["row"], enemy["col"])
            )
            goal = goal_for(enemy["side"], enemy["lane"], nav_map)
            if goal is None:
                enemy["path"] = []
                continue
            path = astar_pathfinding(nav_map, start, goal)
            enemy["path"] = path if path else []
            enemy["path_index"] = 0
            enemy["progress"] = 0.0

    def can_merge_into(self, existing: dict, kind: TowerKind) -> bool:
        return (
            kind.mergeable
            and existing["kind"] == kind.key
            and existing["tier"] < MAX_TIER
            and self.gold >= kind.price
        )

    def try_place_or_merge(self, row: int, col: int) -> str:
        """Returns action taken: place|merge|rotate|blocked|nofunds."""
        kind = TOWER_KINDS[self.selected_kind]
        cell = (row, col)
        if cell in self.towers:
            existing = self.towers[cell]
            if self.can_merge_into(existing, kind):
                self.gold -= kind.price
                existing["tier"] += 1
                existing["cooldown"] = 0.0
                return "merge"
            # Desktop: tap placed Lance to rotate facing
            if existing["kind"] == "lance":
                existing["facing"] = facing_offset(existing.get("facing", "N"), 1)
                return "rotate"
            return "blocked"

        if self.gold < kind.price:
            return "nofunds"
        self.gold -= kind.price
        tower = {
            "kind": kind.key,
            "tier": 1,
            "cooldown": 0.0,
        }
        if kind.key == "lance":
            tower["facing"] = "N"
        self.towers[cell] = tower
        self.recalculate_enemy_paths()
        return "place"

    def on_touch_down(self, touch):
        if self.show_intro:
            self.show_intro = False
            self.draw_grid()
            return True

        x, y = touch.pos
        for key, (tx, ty, tw, th) in self.tray_rects().items():
            if tx <= x <= tx + tw and ty <= y <= ty + th:
                self.selected_kind = key
                self.draw_grid()
                return True

        gx, gy = self.grid_top_left
        if gx <= x < gx + GRIDS_SIZE and gy <= y < gy + GRIDS_SIZE:
            cell_x = int((y - gy) // GRIDS_INTERVAL)
            cell_y = int((x - gx) // GRIDS_INTERVAL)
            self.selected_cell = (cell_x, cell_y)
            self.try_place_or_merge(cell_x, cell_y)
            self.draw_grid()
            return True
        return super().on_touch_down(touch)

    def spawn_enemy(self, *, splitter: bool = False):
        side = random.choice(SIDES)
        lane = random.randint(0, EDGES - 1)
        nav_map = self.build_navigation_map()
        start = start_for(side, lane)
        if not nav_map[start[0]][start[1]]:
            for alt in range(EDGES):
                candidate = start_for(side, alt)
                if nav_map[candidate[0]][candidate[1]]:
                    lane = alt
                    start = candidate
                    break
            else:
                return
        goal = goal_for(side, lane, nav_map)
        if goal is None:
            return
        path = astar_pathfinding(nav_map, start, goal)
        if not path:
            return
        self.wave += 1
        if splitter:
            max_hp = 14 + min(24, self.wave * 0.8)
            enemy = {
                "row": start[0],
                "col": start[1],
                "side": side,
                "lane": lane,
                "progress": 0.0,
                "path": path,
                "path_index": 0,
                "hp": max_hp,
                "max_hp": max_hp,
                "slow": 0.0,
                "splitter": True,
                "minor": False,
                "worth": 10,
            }
        else:
            max_hp = 18 + min(40, self.wave * 1.5)
            enemy = {
                "row": start[0],
                "col": start[1],
                "side": side,
                "lane": lane,
                "progress": 0.0,
                "path": path,
                "path_index": 0,
                "hp": max_hp,
                "max_hp": max_hp,
                "slow": 0.0,
                "splitter": False,
                "minor": False,
                "worth": 8,
            }
        self.enemies.append(enemy)

    def spawn_split_minors(self, parent: dict):
        """Desktop TestEnemy2 — spawn weaker copies on adjacent lanes."""
        side = parent["side"]
        for lane in (parent["lane"] - 1, parent["lane"] + 1):
            if lane not in range(EDGES):
                continue
            nav_map = self.build_navigation_map()
            start = start_for(side, lane)
            # Keep near parent's grid cell if walkable, else lane start
            pref = (parent["row"], parent["col"])
            if 0 <= pref[0] < EDGES and 0 <= pref[1] < EDGES and nav_map[pref[0]][pref[1]]:
                # Nudge to adjacent lane cell
                if side in ("N", "S"):
                    start = (parent["row"], lane)
                else:
                    start = (lane, parent["col"])
                if not (0 <= start[0] < EDGES and 0 <= start[1] < EDGES and nav_map[start[0]][start[1]]):
                    start = start_for(side, lane)
            if not nav_map[start[0]][start[1]]:
                continue
            goal = goal_for(side, lane, nav_map)
            if goal is None:
                continue
            path = astar_pathfinding(nav_map, start, goal)
            if not path:
                continue
            hp = max(3.0, parent["max_hp"] * 0.25)
            self.enemies.append(
                {
                    "row": start[0],
                    "col": start[1],
                    "side": side,
                    "lane": lane,
                    "progress": 0.0,
                    "path": path,
                    "path_index": 0,
                    "hp": hp,
                    "max_hp": hp,
                    "slow": 0.0,
                    "splitter": False,
                    "minor": True,
                    "worth": 3,
                }
            )

    def enemy_world_pos(self, enemy: dict) -> tuple[float, float] | None:
        if not enemy.get("path"):
            return None
        idx = enemy["path_index"]
        prog = enemy["progress"]
        if idx < len(enemy["path"]) - 1:
            r0, c0 = enemy["path"][idx]
            r1, c1 = enemy["path"][idx + 1]
            row = r0 + (r1 - r0) * prog
            col = c0 + (c1 - c0) * prog
        else:
            row, col = enemy["path"][-1]
        return cell_center(self.grid_top_left, row, col)

    def enemies_in_beam(self, x: float, y: float, facing: str, half_width: float) -> list[dict]:
        hit = []
        for enemy in self.enemies:
            pos = self.enemy_world_pos(enemy)
            if pos is None:
                continue
            ex, ey = pos
            if facing == "N" and ey >= y and abs(ex - x) <= half_width:
                hit.append(enemy)
            elif facing == "S" and ey <= y and abs(ex - x) <= half_width:
                hit.append(enemy)
            elif facing == "E" and ex >= x and abs(ey - y) <= half_width:
                hit.append(enemy)
            elif facing == "W" and ex <= x and abs(ey - y) <= half_width:
                hit.append(enemy)
        return hit

    def fire_towers(self, dt: float):
        for (row, col), tower in self.towers.items():
            tower["cooldown"] -= dt
            if tower["cooldown"] > 0:
                continue
            kind = TOWER_KINDS[tower["kind"]]
            tx, ty = cell_center(self.grid_top_left, row, col)
            tier = tower["tier"]

            if kind.key == "cross":
                for facing in FACINGS:
                    vx, vy = FACING_VEC[facing]
                    self.bullets.append(
                        {
                            "kind": "cross",
                            "x": tx,
                            "y": ty,
                            "vx": vx * 220,
                            "vy": vy * 220,
                            "damage": 3.0,
                            "life": 1.2,
                        }
                    )
                tower["cooldown"] = kind.base_interval

            elif kind.key == "lance":
                facing = tower.get("facing", "N")
                for off in LANCE_TRI[tier]:
                    beam_facing = facing_offset(facing, off)
                    self.effects.append(
                        Effect(
                            kind="laser",
                            life=1.2,
                            max_life=1.2,
                            x=tx,
                            y=ty,
                            data={"facing": beam_facing, "dpf": 8.0 + 2.0 * (tier - 1)},
                        )
                    )
                tower["cooldown"] = max(0.7, kind.base_interval * (0.92 ** (tier - 1)))

            elif kind.key == "pulse":
                radius = GRIDS_INTERVAL * 4
                self.effects.append(
                    Effect(
                        kind="pulse",
                        life=0.8,
                        max_life=0.8,
                        x=tx,
                        y=ty,
                        data={"radius": radius, "damage": 6.0, "hit": set()},
                    )
                )
                tower["cooldown"] = kind.base_interval

            elif kind.key == "arc":
                rng = GRIDS_INTERVAL * 4
                target = None
                best_d = rng
                for enemy in self.enemies:
                    pos = self.enemy_world_pos(enemy)
                    if pos is None:
                        continue
                    dist = math.hypot(pos[0] - tx, pos[1] - ty)
                    if dist < best_d:
                        best_d = dist
                        target = enemy
                if target is None:
                    tower["cooldown"] = 0.15
                    continue
                bounces = tier + 1  # desktop: tier + 1
                self._fire_chain(tx, ty, target, rng, bounces, hit_hist=[target])
                tower["cooldown"] = max(0.28, kind.base_interval * (0.9 ** (tier - 1)))

    def _fire_chain(
        self,
        x0: float,
        y0: float,
        target: dict,
        radius: float,
        rest: int,
        hit_hist: list[dict],
    ):
        tpos = self.enemy_world_pos(target)
        if tpos is None:
            return
        target["hp"] -= 4.0
        self.effects.append(
            Effect(
                kind="chain",
                life=0.15,
                max_life=0.15,
                data={"x0": x0, "y0": y0, "x1": tpos[0], "y1": tpos[1]},
            )
        )
        if rest <= 1:
            return
        next_target = None
        best_d = radius
        for enemy in self.enemies:
            if enemy in hit_hist:
                continue
            pos = self.enemy_world_pos(enemy)
            if pos is None:
                continue
            dist = math.hypot(pos[0] - tpos[0], pos[1] - tpos[1])
            if dist < best_d:
                best_d = dist
                next_target = enemy
        if next_target is not None:
            hit_hist.append(next_target)
            self._fire_chain(tpos[0], tpos[1], next_target, radius, rest - 1, hit_hist)

    def update_bullets(self, dt: float):
        alive = []
        for bullet in self.bullets:
            bullet["life"] -= dt
            bullet["x"] += bullet["vx"] * dt
            bullet["y"] += bullet["vy"] * dt
            if (
                bullet["x"] < -10
                or bullet["x"] > WIN_SIZE + 10
                or bullet["y"] < -10
                or bullet["y"] > WIN_SIZE + 10
                or bullet["life"] <= 0
            ):
                continue
            hit_any = False
            for enemy in self.enemies:
                pos = self.enemy_world_pos(enemy)
                if pos and math.hypot(pos[0] - bullet["x"], pos[1] - bullet["y"]) < 12:
                    enemy["hp"] -= bullet["damage"]
                    hit_any = True
                    break
            if not hit_any:
                alive.append(bullet)
        self.bullets = alive

    def update_effects(self, dt: float):
        alive = []
        for fx in self.effects:
            fx.life -= dt
            if fx.kind == "laser":
                # DPS while beam is "hot" (gaussian peak region)
                t = 1.0 - fx.life / fx.max_life
                x = t * 10 - 5
                y = gauss01(x)
                if 0.2 < y < 1.0:
                    half_w = max(6.0, GRIDS_INTERVAL * 0.55 * y)
                    for enemy in self.enemies_in_beam(fx.x, fx.y, fx.data["facing"], half_w):
                        enemy["hp"] -= fx.data["dpf"] * dt
            elif fx.kind == "pulse":
                progress = 1.0 - fx.life / fx.max_life
                r = fx.data["radius"] * progress
                hit_ids = fx.data["hit"]
                for enemy in self.enemies:
                    eid = id(enemy)
                    if eid in hit_ids:
                        continue
                    pos = self.enemy_world_pos(enemy)
                    if pos is None:
                        continue
                    if math.hypot(pos[0] - fx.x, pos[1] - fx.y) <= r + 8:
                        enemy["hp"] -= fx.data["damage"]
                        enemy["slow"] = max(enemy["slow"], 0.5)  # desktop cold ~0.5s feel
                        hit_ids.add(eid)
            if fx.life > 0:
                alive.append(fx)
        self.effects = alive

    def reap_enemies(self):
        survivors = []
        gold = 0
        for enemy in self.enemies:
            if enemy["hp"] <= 0:
                gold += enemy.get("worth", 4)
                if enemy.get("splitter") and not enemy.get("minor"):
                    self.spawn_split_minors(enemy)
            else:
                survivors.append(enemy)
        self.enemies = survivors
        self.gold += gold

    def update(self, dt):
        if self.show_intro:
            self.draw_grid()
            return

        self.spawn_timer += dt
        self.split_timer += dt
        if self.spawn_timer > max(0.85, 2.0 - self.wave * 0.01):
            self.spawn_enemy(splitter=False)
            self.spawn_timer = 0
        if self.split_timer > 3.0:
            self.spawn_enemy(splitter=True)
            self.split_timer = 0

        for enemy in self.enemies:
            if enemy.get("path") and enemy["path_index"] < len(enemy["path"]) - 1:
                speed = 1.35 * dt
                if enemy["slow"] > 0:
                    speed *= 0.5  # desktop cold_modifier
                    enemy["slow"] = max(0.0, enemy["slow"] - dt)
                enemy["progress"] += speed
                while enemy["progress"] >= 1.0 and enemy["path_index"] < len(enemy["path"]) - 1:
                    enemy["path_index"] += 1
                    enemy["progress"] -= 1.0
                r, c = enemy["path"][enemy["path_index"]]
                enemy["row"], enemy["col"] = r, c

        self.fire_towers(dt)
        self.update_bullets(dt)
        self.update_effects(dt)
        self.reap_enemies()

        survivors = []
        for enemy in self.enemies:
            if reached_exit(enemy):
                self.hp -= 1
            else:
                survivors.append(enemy)
        self.enemies = survivors
        self.draw_grid()


class TDApp(App):
    title = "FourWay TD"

    def build(self):
        Window.size = (WIN_SIZE, WIN_SIZE)
        self.game = GameWidget()
        Clock.schedule_interval(self.game.update, 1.0 / 60.0)
        return self.game


if __name__ == "__main__":
    TDApp().run()
