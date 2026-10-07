"""FourWay TD — Kivy / Android build entrypoint.

Enemies spawn from all four cardinal directions and pathfind around towers.
"""

from __future__ import annotations

import random

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from pathfinding import astar_pathfinding

WIN_SIZE = 600
GRIDS_SIZE = 200
EDGES = 5
GRIDS_INTERVAL = GRIDS_SIZE / EDGES
ROAD_LENGTH = (WIN_SIZE - GRIDS_SIZE) / 2

# side -> (start_row_or_None, start_col_or_None, goal_row_or_None, goal_col_or_None)
# For a given side, the varying axis uses `lane` (0..EDGES-1).
SIDES = ("N", "E", "S", "W")


def start_for(side: str, lane: int) -> tuple[int, int]:
    if side == "N":
        return (0, lane)
    if side == "S":
        return (EDGES - 1, lane)
    if side == "W":
        return (lane, 0)
    return (lane, EDGES - 1)  # E


def goal_for(side: str, lane: int, nav_map: list[list[bool]]) -> tuple[int, int] | None:
    """Opposite edge; prefer the same lane, else first walkable cell on that edge."""
    if side == "N":
        edge = [(EDGES - 1, c) for c in range(EDGES)]
        preferred = (EDGES - 1, lane)
    elif side == "S":
        edge = [(0, c) for c in range(EDGES)]
        preferred = (0, lane)
    elif side == "W":
        edge = [(r, EDGES - 1) for r in range(EDGES)]
        preferred = (lane, EDGES - 1)
    else:  # E
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


class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (WIN_SIZE, WIN_SIZE)
        self.grid_top_left = (ROAD_LENGTH, ROAD_LENGTH)
        self.selected_cell = None
        self.towers: list[tuple[int, int]] = []
        self.enemies: list[dict] = []
        self.spawn_timer = 0.0
        self.hp = 20
        self.gold = 100
        self.show_intro = True
        self.intro_timer = 0.0

        self.hp_label = Label(
            text=f"HP: {self.hp}",
            size_hint=(None, None),
            pos=(10, WIN_SIZE - 30),
            color=(1, 0, 0, 1),
            font_size=20,
        )
        self.gold_label = Label(
            text=f"Gold: {self.gold}",
            size_hint=(None, None),
            pos=(120, WIN_SIZE - 30),
            color=(1, 0.84, 0, 1),
            font_size=20,
        )
        self.title_label = Label(
            text="FOURWAY TD",
            size_hint=(None, None),
            size=(WIN_SIZE, 40),
            pos=(0, WIN_SIZE - 70),
            color=(0.08, 0.14, 0.2, 1),
            font_size=22,
            bold=True,
        )
        self.hint_label = Label(
            text="Tap grid to place · enemies from N E S W",
            size_hint=(None, None),
            size=(WIN_SIZE, 28),
            pos=(0, 8),
            color=(0.08, 0.14, 0.2, 0.85),
            font_size=14,
        )
        self.add_widget(self.hp_label)
        self.add_widget(self.gold_label)
        self.add_widget(self.title_label)
        self.add_widget(self.hint_label)
        self.draw_grid()

    def draw_grid(self):
        self.canvas.clear()
        with self.canvas:
            # Approach roads from four sides
            Color(0.12, 0.18, 0.26, 0.35)
            # North / south corridors
            for i in range(EDGES):
                x = self.grid_top_left[0] + i * GRIDS_INTERVAL
                Rectangle(pos=(x + 4, 0), size=(GRIDS_INTERVAL - 8, ROAD_LENGTH))
                Rectangle(
                    pos=(x + 4, self.grid_top_left[1] + GRIDS_SIZE),
                    size=(GRIDS_INTERVAL - 8, ROAD_LENGTH),
                )
            # West / east corridors
            for i in range(EDGES):
                y = self.grid_top_left[1] + i * GRIDS_INTERVAL
                Rectangle(pos=(0, y + 4), size=(ROAD_LENGTH, GRIDS_INTERVAL - 8))
                Rectangle(
                    pos=(self.grid_top_left[0] + GRIDS_SIZE, y + 4),
                    size=(ROAD_LENGTH, GRIDS_INTERVAL - 8),
                )

            Color(0.68, 0.83, 0.64, 1)
            Rectangle(
                pos=self.grid_top_left,
                size=(GRIDS_SIZE, GRIDS_SIZE),
            )

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

            for cell_x, cell_y in self.towers:
                Color(1, 0.85, 0.2, 1)
                Ellipse(
                    pos=(
                        self.grid_top_left[0] + cell_y * GRIDS_INTERVAL + GRIDS_INTERVAL * 0.1,
                        self.grid_top_left[1] + cell_x * GRIDS_INTERVAL + GRIDS_INTERVAL * 0.1,
                    ),
                    size=(GRIDS_INTERVAL * 0.8, GRIDS_INTERVAL * 0.8),
                )

            for enemy in self.enemies:
                if "path" in enemy and enemy["path"]:
                    idx = enemy["path_index"]
                    prog = enemy["progress"]
                    if idx < len(enemy["path"]) - 1:
                        r0, c0 = enemy["path"][idx]
                        r1, c1 = enemy["path"][idx + 1]
                        row = r0 + (r1 - r0) * prog
                        col = c0 + (c1 - c0) * prog
                    else:
                        row, col = enemy["path"][-1]
                    y = self.grid_top_left[1] + row * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
                    x = self.grid_top_left[0] + col * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
                    Color(0.85, 0.15, 0.15, 1)
                    Ellipse(
                        pos=(x - GRIDS_INTERVAL * 0.3, y - GRIDS_INTERVAL * 0.3),
                        size=(GRIDS_INTERVAL * 0.6, GRIDS_INTERVAL * 0.6),
                    )

            if self.selected_cell:
                x, y = self.selected_cell
                Color(1, 1, 0, 0.28)
                Rectangle(
                    pos=(
                        self.grid_top_left[0] + y * GRIDS_INTERVAL,
                        self.grid_top_left[1] + x * GRIDS_INTERVAL,
                    ),
                    size=(GRIDS_INTERVAL, GRIDS_INTERVAL),
                )

            if self.show_intro:
                Color(0.06, 0.1, 0.16, 0.72)
                Rectangle(pos=(0, 0), size=(WIN_SIZE, WIN_SIZE))
                Color(0.95, 0.96, 0.92, 1)
                Rectangle(pos=(60, WIN_SIZE / 2 - 70), size=(WIN_SIZE - 120, 140))

        self.hp_label.text = f"HP: {self.hp}"
        self.gold_label.text = f"Gold: {self.gold}"
        if self.show_intro:
            self.title_label.text = "FOURWAY TD"
            self.hint_label.text = "Tap anywhere — defend N · E · S · W"
            self.title_label.pos = (0, WIN_SIZE / 2 - 10)
            self.hint_label.pos = (0, WIN_SIZE / 2 - 45)
        else:
            self.title_label.pos = (0, WIN_SIZE - 70)
            self.hint_label.pos = (0, 8)
            self.hint_label.text = "Tap grid to place · 10 gold · four fronts"

    def build_navigation_map(self):
        nav_map = [[True for _ in range(EDGES)] for _ in range(EDGES)]
        for x, y in self.towers:
            nav_map[x][y] = False
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

    def on_touch_down(self, touch):
        if self.show_intro:
            self.show_intro = False
            self.draw_grid()
            return True

        x, y = touch.pos
        gx, gy = self.grid_top_left
        if gx <= x < gx + GRIDS_SIZE and gy <= y < gy + GRIDS_SIZE:
            cell_x = int((y - gy) // GRIDS_INTERVAL)
            cell_y = int((x - gx) // GRIDS_INTERVAL)
            self.selected_cell = (cell_x, cell_y)
            if (cell_x, cell_y) not in self.towers and self.gold >= 10:
                self.towers.append((cell_x, cell_y))
                self.gold -= 10
                self.recalculate_enemy_paths()
            self.draw_grid()
        return super().on_touch_down(touch)

    def spawn_enemy(self):
        side = random.choice(SIDES)
        lane = random.randint(0, EDGES - 1)
        nav_map = self.build_navigation_map()
        start = start_for(side, lane)
        # If start cell is blocked, try another lane quickly
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
        self.enemies.append(
            {
                "row": start[0],
                "col": start[1],
                "side": side,
                "lane": lane,
                "progress": 0.0,
                "path": path,
                "path_index": 0,
            }
        )

    def update(self, dt):
        if self.show_intro:
            self.intro_timer += dt
            self.draw_grid()
            return

        self.spawn_timer += dt
        if self.spawn_timer > 2.0:
            self.spawn_enemy()
            self.spawn_timer = 0

        speed = 1.5 * dt
        for enemy in self.enemies:
            if enemy.get("path") and enemy["path_index"] < len(enemy["path"]) - 1:
                enemy["progress"] += speed
                while enemy["progress"] >= 1.0 and enemy["path_index"] < len(enemy["path"]) - 1:
                    enemy["path_index"] += 1
                    enemy["progress"] -= 1.0
                r, c = enemy["path"][enemy["path_index"]]
                enemy["row"], enemy["col"] = r, c

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
