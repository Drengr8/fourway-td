from kivy.app import App
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.uix.label import Label
from pathfinding import astar_pathfinding
from kivy.uix.floatlayout import FloatLayout

# Constants (should match your const.py)
WIN_SIZE = 600
GRIDS_SIZE = 200
EDGES = 5
GRIDS_INTERVAL = GRIDS_SIZE / EDGES
ROAD_LENGTH = (WIN_SIZE - GRIDS_SIZE) / 2
TOWER_GRID_SIZE = GRIDS_INTERVAL

class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (WIN_SIZE, WIN_SIZE)
        self.grid_top_left = (ROAD_LENGTH, ROAD_LENGTH)
        self.selected_cell = None
        self.draw_grid()
        # Placeholder for towers, etc.
        self.towers = []  # List of (cell_x, cell_y)
        self.enemies = []  # List of {'row': int, 'col': int, 'progress': float, 'path': list}
        self.spawn_timer = 0
        self.last_tower_count = 0
        # Resources
        self.hp = 20
        self.gold = 100
        # UI Labels
        self.hp_label = Label(text=f"HP: {self.hp}", size_hint=(None, None), pos=(10, WIN_SIZE-30), color=(1,0,0,1), font_size=20)
        self.gold_label = Label(text=f"Gold: {self.gold}", size_hint=(None, None), pos=(120, WIN_SIZE-30), color=(1,0.84,0,1), font_size=20)
        self.add_widget(self.hp_label)
        self.add_widget(self.gold_label)

    def draw_grid(self):
        from kivy.graphics import Color, Line, Rectangle, Ellipse
        self.canvas.clear()
        with self.canvas:
            Color(0.08, 0.14, 0.2, 1)  # Grid line color
            for i in range(EDGES + 1):
                # Horizontal
                Line(points=[
                    self.grid_top_left[0],
                    self.grid_top_left[1] + i * GRIDS_INTERVAL,
                    self.grid_top_left[0] + GRIDS_SIZE,
                    self.grid_top_left[1] + i * GRIDS_INTERVAL
                ], width=1)
                # Vertical
                Line(points=[
                    self.grid_top_left[0] + i * GRIDS_INTERVAL,
                    self.grid_top_left[1],
                    self.grid_top_left[0] + i * GRIDS_INTERVAL,
                    self.grid_top_left[1] + GRIDS_SIZE
                ], width=1)
            # Draw towers
            for cell_x, cell_y in self.towers:
                Color(1, 0.85, 0.2, 1)  # Tower color (yellowish)
                Ellipse(
                    pos=(self.grid_top_left[0] + cell_y * GRIDS_INTERVAL + GRIDS_INTERVAL * 0.1,
                         self.grid_top_left[1] + cell_x * GRIDS_INTERVAL + GRIDS_INTERVAL * 0.1),
                    size=(GRIDS_INTERVAL * 0.8, GRIDS_INTERVAL * 0.8)
                )
            # Draw enemies
            for enemy in self.enemies:
                # Interpolate position between path nodes based on progress
                if 'path' in enemy and enemy['path']:
                    idx = enemy['path_index']
                    prog = enemy['progress']
                    if idx < len(enemy['path']) - 1:
                        r0, c0 = enemy['path'][idx]
                        r1, c1 = enemy['path'][idx + 1]
                        row = r0 + (r1 - r0) * prog
                        col = c0 + (c1 - c0) * prog
                    else:
                        row, col = enemy['path'][-1]
                    y = self.grid_top_left[1] + row * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
                    x = self.grid_top_left[0] + col * GRIDS_INTERVAL + GRIDS_INTERVAL / 2
                    Color(1, 0.2, 0.2, 1)  # Enemy color (red)
                    Ellipse(
                        pos=(x - GRIDS_INTERVAL * 0.3, y - GRIDS_INTERVAL * 0.3),
                        size=(GRIDS_INTERVAL * 0.6, GRIDS_INTERVAL * 0.6)
                    )
            # Highlight selected cell
            if self.selected_cell:
                x, y = self.selected_cell
                Color(1, 1, 0, 0.3)
                Rectangle(
                    pos=(self.grid_top_left[0] + y * GRIDS_INTERVAL, self.grid_top_left[1] + x * GRIDS_INTERVAL),
                    size=(GRIDS_INTERVAL, GRIDS_INTERVAL)
                )
        # Update UI labels
        self.hp_label.text = f"HP: {self.hp}"
        self.gold_label.text = f"Gold: {self.gold}"

    def build_navigation_map(self):
        # True = walkable, False = blocked
        nav_map = [[True for _ in range(EDGES)] for _ in range(EDGES)]
        for x, y in self.towers:
            nav_map[x][y] = False
        return nav_map

    def recalculate_enemy_paths(self):
        nav_map = self.build_navigation_map()
        for enemy in self.enemies:
            start = enemy['path'][enemy['path_index']] if 'path' in enemy and enemy['path'] else (enemy['row'], enemy['col'])
            goal_row = EDGES - 1
            goal = None
            # Find the first walkable cell in the bottom row
            for c in range(EDGES):
                if nav_map[goal_row][c]:
                    goal = (goal_row, c)
                    break
            if goal is None:
                enemy['path'] = []
                continue
            path = astar_pathfinding(nav_map, start, goal)
            enemy['path'] = path if path else []
            enemy['path_index'] = 0
            enemy['progress'] = 0.0

    def on_touch_down(self, touch):
        # Check if touch is inside the grid
        x, y = touch.pos
        gx, gy = self.grid_top_left
        if gx <= x < gx + GRIDS_SIZE and gy <= y < gy + GRIDS_SIZE:
            cell_x = int((y - gy) // GRIDS_INTERVAL)
            cell_y = int((x - gx) // GRIDS_INTERVAL)
            self.selected_cell = (cell_x, cell_y)
            # Place tower if not already present and if enough gold
            if (cell_x, cell_y) not in self.towers and self.gold >= 10:
                self.towers.append((cell_x, cell_y))
                self.gold -= 10
                self.recalculate_enemy_paths()
            self.draw_grid()
        return super().on_touch_down(touch)

    def update(self, dt):
        # Spawn a new enemy every 2 seconds
        self.spawn_timer += dt
        if self.spawn_timer > 2.0:
            import random
            col = random.randint(0, EDGES - 1)
            nav_map = self.build_navigation_map()
            start = (0, col)
            goal_row = EDGES - 1
            goal = None
            for c in range(EDGES):
                if nav_map[goal_row][c]:
                    goal = (goal_row, c)
                    break
            if goal is not None:
                path = astar_pathfinding(nav_map, start, goal)
                if path:
                    self.enemies.append({'row': 0, 'col': col, 'progress': 0.0, 'path': path, 'path_index': 0})
            self.spawn_timer = 0
        # Move enemies along their path
        speed = 1.5 * dt  # cells per second
        for enemy in self.enemies:
            if 'path' in enemy and enemy['path'] and enemy['path_index'] < len(enemy['path']) - 1:
                enemy['progress'] += speed
                while enemy['progress'] >= 1.0 and enemy['path_index'] < len(enemy['path']) - 1:
                    enemy['path_index'] += 1
                    enemy['progress'] -= 1.0
                # Update row/col for removal logic
                r, c = enemy['path'][enemy['path_index']]
                enemy['row'], enemy['col'] = r, c
        # Remove enemies that reach the bottom row
        new_enemies = []
        for e in self.enemies:
            if e.get('path') and e['path_index'] == len(e['path']) - 1 and e['row'] == EDGES - 1:
                self.hp -= 1
            else:
                new_enemies.append(e)
        self.enemies = new_enemies
        self.draw_grid()

class TDApp(App):
    def build(self):
        Window.size = (WIN_SIZE, WIN_SIZE)
        self.game = GameWidget()
        Clock.schedule_interval(self.game.update, 1.0 / 60.0)
        return self.game

if __name__ == '__main__':
    TDApp().run()
