"""FourWay TD — Kivy / Android build entrypoint.

Enemies spawn from all four sides. Place and merge towers to escalate tiers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

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
TRAY_H = 72
MAX_TIER = 4
SIDES = ("N", "E", "S", "W")


@dataclass(frozen=True)
class TowerKind:
    key: str
    name: str
    price: int
    color: tuple[float, float, float]
    mergeable: bool
    base_interval: float  # seconds between shots
    base_damage: float
    base_range: float  # in cells


TOWER_KINDS = {
    "bolt": TowerKind(
        "bolt", "Bolt", 10, (1.0, 0.84, 0.2), True, 0.85, 8.0, 2.6
    ),
    "frost": TowerKind(
        "frost", "Frost", 12, (0.35, 0.85, 0.95), True, 1.2, 5.0, 2.2
    ),
    "beam": TowerKind(
        "beam", "Beam", 15, (0.25, 0.45, 0.95), True, 0.55, 4.0, 3.2
    ),
}


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


class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (WIN_SIZE, WIN_SIZE)
        self.grid_top_left = (ROAD_LENGTH, ROAD_LENGTH + TRAY_H * 0.15)
        # Keep grid centered-ish with tray at bottom
        self.grid_top_left = (ROAD_LENGTH, ROAD_LENGTH)
        self.selected_cell = None
        self.selected_kind = "bolt"
        self.towers: dict[tuple[int, int], dict] = {}
        self.enemies: list[dict] = []
        self.bullets: list[dict] = []
        self.spawn_timer = 0.0
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
            text="Select a tower · tap to place · tap same type to merge",
            size_hint=(None, None),
            size=(WIN_SIZE, 26),
            pos=(0, TRAY_H + 6),
            color=(0.08, 0.14, 0.2, 0.9),
            font_size=13,
        )
        self.tier_labels: dict[tuple[int, int], Label] = {}
        self.add_widget(self.hp_label)
        self.add_widget(self.gold_label)
        self.add_widget(self.title_label)
        self.add_widget(self.hint_label)
        self.draw_grid()

    def tray_rects(self) -> dict[str, tuple[float, float, float, float]]:
        keys = list(TOWER_KINDS)
        pad = 12
        slot_w = (WIN_SIZE - pad * (len(keys) + 1)) / len(keys)
        rects = {}
        for i, key in enumerate(keys):
            x = pad + i * (slot_w + pad)
            y = 10
            rects[key] = (x, y, slot_w, TRAY_H - 16)
        return rects

    def sync_tier_labels(self):
        live = set(self.towers)
        for cell, label in list(self.tier_labels.items()):
            if cell not in live:
                self.remove_widget(label)
                del self.tier_labels[cell]
        for (row, col), tower in self.towers.items():
            x, y = cell_center(self.grid_top_left, row, col)
            text = str(tower["tier"])
            if (row, col) not in self.tier_labels:
                label = Label(
                    text=text,
                    size_hint=(None, None),
                    size=(GRIDS_INTERVAL, GRIDS_INTERVAL),
                    pos=(x - GRIDS_INTERVAL / 2, y - GRIDS_INTERVAL / 2),
                    color=(0.05, 0.08, 0.12, 1),
                    font_size=16,
                    bold=True,
                )
                self.tier_labels[(row, col)] = label
                self.add_widget(label)
            else:
                label = self.tier_labels[(row, col)]
                label.text = text
                label.pos = (x - GRIDS_INTERVAL / 2, y - GRIDS_INTERVAL / 2)

    def draw_grid(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.12, 0.18, 0.26, 0.3)
            for i in range(EDGES):
                x = self.grid_top_left[0] + i * GRIDS_INTERVAL
                Rectangle(pos=(x + 4, 0 + TRAY_H), size=(GRIDS_INTERVAL - 8, ROAD_LENGTH - 8))
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
                pad = GRIDS_INTERVAL * (0.18 - 0.02 * (tower["tier"] - 1))
                x = self.grid_top_left[0] + col * GRIDS_INTERVAL + pad
                y = self.grid_top_left[1] + row * GRIDS_INTERVAL + pad
                size = GRIDS_INTERVAL - pad * 2
                if kind.key == "frost":
                    Triangle(
                        points=[
                            x + size / 2, y + size,
                            x, y,
                            x + size, y,
                        ]
                    )
                elif kind.key == "beam":
                    Rectangle(pos=(x, y), size=(size, size))
                else:
                    Ellipse(pos=(x, y), size=(size, size))

            for enemy in self.enemies:
                if not enemy.get("path"):
                    continue
                idx = enemy["path_index"]
                prog = enemy["progress"]
                if idx < len(enemy["path"]) - 1:
                    r0, c0 = enemy["path"][idx]
                    r1, c1 = enemy["path"][idx + 1]
                    row = r0 + (r1 - r0) * prog
                    col = c0 + (c1 - c0) * prog
                else:
                    row, col = enemy["path"][-1]
                x, y = cell_center(self.grid_top_left, row, col)
                hp_ratio = max(0.15, enemy["hp"] / enemy["max_hp"])
                Color(0.85, 0.15 + 0.2 * (1 - hp_ratio), 0.15, 1)
                r = GRIDS_INTERVAL * 0.28
                Ellipse(pos=(x - r, y - r), size=(r * 2, r * 2))

            for bullet in self.bullets:
                Color(1, 1, 1, 0.9)
                Ellipse(pos=(bullet["x"] - 3, bullet["y"] - 3), size=(6, 6))

            # Tray
            Color(0.08, 0.12, 0.18, 0.92)
            Rectangle(pos=(0, 0), size=(WIN_SIZE, TRAY_H))
            for key, (x, y, w, h) in self.tray_rects().items():
                kind = TOWER_KINDS[key]
                selected = key == self.selected_kind
                Color(*(kind.color if selected else (0.25, 0.3, 0.36)), 1)
                Rectangle(pos=(x, y), size=(w, h))
                Color(0.05, 0.08, 0.12, 1)
                if selected:
                    Line(rectangle=(x, y, w, h), width=2)

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
                Rectangle(pos=(50, WIN_SIZE / 2 - 80), size=(WIN_SIZE - 100, 160))

        self.hp_label.text = f"HP: {self.hp}"
        self.gold_label.text = f"Gold: {self.gold}"
        if self.show_intro:
            self.title_label.text = "FOURWAY TD"
            self.hint_label.text = "Tap — place, merge tiers, hold N·E·S·W"
            self.title_label.pos = (0, WIN_SIZE / 2 - 5)
            self.hint_label.pos = (0, WIN_SIZE / 2 - 40)
        else:
            self.title_label.pos = (0, WIN_SIZE - 68)
            self.hint_label.pos = (0, TRAY_H + 6)
            kind = TOWER_KINDS[self.selected_kind]
            self.hint_label.text = (
                f"{kind.name} selected · {kind.price}g · same type merges to T{MAX_TIER}"
            )
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

    def try_place_or_merge(self, row: int, col: int):
        kind = TOWER_KINDS[self.selected_kind]
        cell = (row, col)
        if cell in self.towers:
            existing = self.towers[cell]
            if (
                kind.mergeable
                and existing["kind"] == kind.key
                and existing["tier"] < MAX_TIER
                and self.gold >= kind.price
            ):
                self.gold -= kind.price
                existing["tier"] += 1
                existing["cooldown"] = 0.0
                return True
            return False

        if self.gold < kind.price:
            return False
        self.gold -= kind.price
        self.towers[cell] = {
            "kind": kind.key,
            "tier": 1,
            "cooldown": 0.0,
        }
        self.recalculate_enemy_paths()
        return True

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

    def spawn_enemy(self):
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
        max_hp = 18 + min(40, self.wave * 1.5)
        self.enemies.append(
            {
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

    def tower_stats(self, tower: dict) -> tuple[float, float, float]:
        kind = TOWER_KINDS[tower["kind"]]
        tier = tower["tier"]
        interval = max(0.25, kind.base_interval * (0.85 ** (tier - 1)))
        damage = kind.base_damage * (1.0 + 0.55 * (tier - 1))
        rng = kind.base_range * (1.0 + 0.12 * (tier - 1))
        return interval, damage, rng

    def fire_towers(self, dt: float):
        for (row, col), tower in self.towers.items():
            tower["cooldown"] -= dt
            if tower["cooldown"] > 0:
                continue
            interval, damage, rng = self.tower_stats(tower)
            tx, ty = cell_center(self.grid_top_left, row, col)
            best = None
            best_d = rng * GRIDS_INTERVAL
            for enemy in self.enemies:
                pos = self.enemy_world_pos(enemy)
                if pos is None:
                    continue
                dist = math.hypot(pos[0] - tx, pos[1] - ty)
                if dist <= best_d:
                    best_d = dist
                    best = enemy
            if best is None:
                continue
            target_pos = self.enemy_world_pos(best)
            if target_pos is None:
                continue
            kind = TOWER_KINDS[tower["kind"]]
            self.bullets.append(
                {
                    "x": tx,
                    "y": ty,
                    "tx": target_pos[0],
                    "ty": target_pos[1],
                    "damage": damage,
                    "kind": kind.key,
                    "target": best,
                    "life": 0.35,
                }
            )
            tower["cooldown"] = interval

    def update_bullets(self, dt: float):
        alive = []
        for bullet in self.bullets:
            bullet["life"] -= dt
            # Lerp toward target position
            bullet["x"] += (bullet["tx"] - bullet["x"]) * min(1.0, dt * 14)
            bullet["y"] += (bullet["ty"] - bullet["y"]) * min(1.0, dt * 14)
            target = bullet["target"]
            if target in self.enemies:
                pos = self.enemy_world_pos(target)
                if pos and math.hypot(pos[0] - bullet["x"], pos[1] - bullet["y"]) < 14:
                    target["hp"] -= bullet["damage"]
                    if bullet["kind"] == "frost":
                        target["slow"] = max(target["slow"], 0.55)
                    continue
            if bullet["life"] > 0:
                alive.append(bullet)
        self.bullets = alive
        self.enemies = [e for e in self.enemies if e["hp"] > 0]
        # Gold for kills already removed — pay on death:
        # handled by counting removals above would need previous set; keep simple:
        # award small gold when enemy list shrinks via combat in update()

    def update(self, dt):
        if self.show_intro:
            self.draw_grid()
            return

        before = len(self.enemies)
        self.spawn_timer += dt
        if self.spawn_timer > max(0.9, 2.0 - self.wave * 0.01):
            self.spawn_enemy()
            self.spawn_timer = 0

        for enemy in self.enemies:
            if enemy.get("path") and enemy["path_index"] < len(enemy["path"]) - 1:
                speed = 1.35 * dt
                if enemy["slow"] > 0:
                    speed *= 0.45
                    enemy["slow"] = max(0.0, enemy["slow"] - dt)
                enemy["progress"] += speed
                while enemy["progress"] >= 1.0 and enemy["path_index"] < len(enemy["path"]) - 1:
                    enemy["path_index"] += 1
                    enemy["progress"] -= 1.0
                r, c = enemy["path"][enemy["path_index"]]
                enemy["row"], enemy["col"] = r, c

        self.fire_towers(dt)
        kills_before = len(self.enemies)
        self.update_bullets(dt)
        killed = kills_before - len(self.enemies)
        if killed > 0:
            self.gold += killed * 4

        survivors = []
        for enemy in self.enemies:
            if reached_exit(enemy):
                self.hp -= 1
            else:
                survivors.append(enemy)
        self.enemies = survivors
        # silence unused
        _ = before
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
