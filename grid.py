from tower import *
from enemy import recalculate_paths
from typing import Optional


class Grids(pygame.sprite.Sprite):
    def __init__(self, size: int, edges: int) -> None:
        super().__init__()
        self.image = pygame.Surface(V_SIZE)
        self.image.set_colorkey(Black)
        self.size = pygame.Vector2(size)
        self.interval = pygame.Vector2(GRIDS_INTERVAL)
        self.top_left_pos = (V_SIZE - pygame.Vector2(size)) / 2
        self.rect = self.image.get_rect(center=pygame.Vector2(V_SIZE) / 2)
        self.edges = edges
        # Navigation map: 2D array, True=walkable, False=blocked
        self.navigation_map = [[True for _ in range(edges)] for _ in range(edges)]
        for e in range(0, edges + 1):
            pygame.draw.line(
                self.image,
                Line,
                pygame.Vector2(0, self.top_left_pos.y + e * self.interval.y),
                pygame.Vector2(WIN_SIZE, self.top_left_pos.y + e * self.interval.y),
                1,
            )
            pygame.draw.line(
                self.image,
                Line,
                pygame.Vector2(self.top_left_pos.x + e * self.interval.x, 0),
                pygame.Vector2(self.top_left_pos.x + e * self.interval.x, WIN_SIZE),
                1,
            )
        for i in range(edges**2):
            x, y = i // edges, i % edges
            if not HAVE_CORNER:
                if (x, y) in [
                    (0, 0),
                    (0, edges - 1),
                    (edges - 1, 0),
                    (edges - 1, edges - 1),
                ]:
                    continue
            coordinate = (x, y)
            pos = self.top_left_pos + pygame.Vector2(
                GRIDS_INTERVAL * (0.5 + y), GRIDS_INTERVAL * (0.5 + x)
            )
            grids.add(Grid(pos=pos, coordinate=coordinate, parent=self))

    def set_blocked(self, x, y, blocked=True):
        self.navigation_map[x][y] = not blocked

    def is_walkable(self, x, y):
        return self.navigation_map[x][y]

    def reset_navigation_map(self):
        for x in range(self.edges):
            for y in range(self.edges):
                self.navigation_map[x][y] = True


class Grid(pygame.sprite.Sprite):
    def __init__(self, pos: pygame.Vector2, coordinate: tuple, parent=None) -> None:
        super().__init__()
        self.image = pygame.Surface([GRIDS_INTERVAL, GRIDS_INTERVAL])
        self.image.set_colorkey(Black)
        self.image.fill(BaseColor)
        self.pos = pos
        self.rect = self.image.get_rect(center=self.pos)
        self.cord = coordinate
        self.tower: Optional[BaseTower] = None
        self.parent = parent  # Reference to Grids

    def available(self, tower: BaseTower):
        if self.tower:
            return self.tower.can_merge(tower)
        else:
            return True

    def place(self, tower: BaseTower):
        if self.tower:
            self.tower.merge(tower)
        else:
            self.tower = tower
            tower.pos = self.pos
            tower.rect.center = self.pos
            tower.placed = True
            # Mark this cell as blocked in the navigation map
            if self.parent:
                x, y = self.cord
                self.parent.set_blocked(x, y, blocked=True)
            # Recalculate all enemy paths
            recalculate_paths()
