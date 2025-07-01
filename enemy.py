from const import *
from const import Direction
from groups import *
from pathfinding import astar_pathfinding
import pygame


class BaseEnemy(pygame.sprite.Sprite):
    """
    敌人基类
    road: 出现在第几路
    side: 出现在哪一侧
    """

    def __init__(
        self,
        road: int,
        side: Direction,
        speed_factor: float = 1,
        power_factor: float = 1,
    ) -> None:
        super().__init__()
        if road not in range(EDGES):
            raise ValueError()
        self.road = road
        self.side = side
        x, y = 0, 0
        self.x_limit, self.y_limit = 0, 0
        match self.side:
            case Direction.UP:
                x = ROAD_LENGTH + ENEMY_SIZE // 2 + self.road * GRIDS_INTERVAL
                y = 0 - ENEMY_SIZE // 2
                self.y_limit = ROAD_LENGTH - ENEMY_SIZE // 2
            case Direction.DOWN:
                x = ROAD_LENGTH + ENEMY_SIZE // 2 + self.road * GRIDS_INTERVAL
                y = WIN_SIZE + ENEMY_SIZE // 2
                self.y_limit = WIN_SIZE - ROAD_LENGTH + ENEMY_SIZE // 2
            case Direction.LEFT:
                x = 0 - ENEMY_SIZE // 2
                y = ROAD_LENGTH + ENEMY_SIZE // 2 + self.road * GRIDS_INTERVAL
                self.x_limit = ROAD_LENGTH - ENEMY_SIZE // 2
            case Direction.RIGHT:
                x = WIN_SIZE + ENEMY_SIZE // 2
                y = ROAD_LENGTH + ENEMY_SIZE // 2 + self.road * GRIDS_INTERVAL
                self.x_limit = WIN_SIZE - ROAD_LENGTH + ENEMY_SIZE // 2

        self.pos = pygame.Vector2(x, y)
        self.speed_modifier = speed_factor
        self.power_factor = power_factor
        self.image = pygame.Surface([ENEMY_SIZE, ENEMY_SIZE])
        self.image.set_colorkey(Black)
        self.rect = self.image.get_rect(center=self.pos)
        self.init_time = pygame.time.get_ticks()

        self.buff = {}
        # Pathfinding
        self.path = self.calculate_path()
        self.path_index = 0
        self.reached_goal = False

    def world_to_grid(self, pos):
        # Convert world position to grid coordinates
        # Use the same logic as Grids for placement
        grids_instance = None
        for g in grid:
            grids_instance = g
            break
        if not grids_instance:
            return (0, 0)
        rel = pos - grids_instance.top_left_pos
        x = int(rel.y // GRIDS_INTERVAL)
        y = int(rel.x // GRIDS_INTERVAL)
        return (x, y)

    def grid_to_world(self, coord):
        # Convert grid coordinates to world position (center of cell)
        grids_instance = None
        for g in grid:
            grids_instance = g
            break
        if not grids_instance:
            return pygame.Vector2(0, 0)
        x, y = coord
        return grids_instance.top_left_pos + pygame.Vector2(GRIDS_INTERVAL * (y + 0.5), GRIDS_INTERVAL * (x + 0.5))

    def get_goal(self):
        # For now, goal is the cell on the opposite edge
        if self.side == Direction.UP:
            return (EDGES - 1, self.road)
        elif self.side == Direction.DOWN:
            return (0, self.road)
        elif self.side == Direction.LEFT:
            return (self.road, EDGES - 1)
        elif self.side == Direction.RIGHT:
            return (self.road, 0)
        else:
            return (EDGES // 2, EDGES // 2)

    def calculate_path(self):
        grids_instance = None
        for g in grid:
            grids_instance = g
            break
        if not grids_instance:
            return []
        nav_map = grids_instance.navigation_map
        start = self.world_to_grid(self.pos)
        goal = self.get_goal()
        path = astar_pathfinding(nav_map, start, goal)
        return path if path else []

    def blink(
        self, *, x: float = 0, y: float = 0, by_x: bool = False, by_y: bool = False
    ):
        if by_x:
            self.pos.x = x
        if by_y:
            self.pos.y = y
        self.rect.center = self.pos

    def on_death(self, worth):
        texts.add(
            FloatText(
                self.pos,
                pygame.font.SysFont("timesnewroman", 12),
                Golden,
                f"+{worth} gold",
            )
        )
        RESOURCE.gold += worth

    def update(self) -> None:
        if self.reached_goal or not self.path or self.path_index >= len(self.path):
            return
        # Move toward next cell in path
        target_coord = self.path[self.path_index]
        target_pos = self.grid_to_world(target_coord)
        direction = (target_pos - self.pos)
        distance = direction.length()
        if distance < 1:
            # Arrived at this cell, go to next
            self.path_index += 1
            if self.path_index >= len(self.path):
                # Reached goal
                self.reached_goal = True
                RESOURCE.hp -= 1
                self.kill()
                return
            target_coord = self.path[self.path_index]
            target_pos = self.grid_to_world(target_coord)
            direction = (target_pos - self.pos)
            distance = direction.length()
        if distance != 0:
            direction = direction.normalize()
        else:
            direction = pygame.Vector2(0, 0)
        # Apply buffs
        if "cold" in self.buff:
            if pygame.time.get_ticks() - self.buff["cold"] < 500:
                cold_modifier = 0.5
            else:
                self.buff.pop("cold", 1)
                cold_modifier = 1
        else:
            cold_modifier = 1
        self.pos += direction * self.speed_modifier * cold_modifier
        self.rect.center = self.pos


class TestEnemy1(BaseEnemy):
    """基础敌人，无特殊能力"""

    def __init__(
        self,
        road: int,
        side: Direction,
        speed_factor: float = 1,
        power_factor: float = 1,
    ) -> None:
        super().__init__(road, side, speed_factor, power_factor)
        pygame.draw.circle(
            self.image, Red, (ENEMY_SIZE // 2, ENEMY_SIZE // 2), ENEMY_SIZE * 0.8 // 2
        )
        pygame.draw.circle(
            self.image,
            AlmostBlack,
            (ENEMY_SIZE // 2, ENEMY_SIZE // 2),
            ENEMY_SIZE * 0.8 // 2,
            1,
        )
        self.mask = pygame.mask.from_surface(self.image)
        self.hp = 10 * self.power_factor
        self.worth = 10

    def update(self) -> None:
        super().update()
        if self.hp <= 0:
            super().on_death(self.worth)
            self.kill()


class TestEnemy2(BaseEnemy):
    """分裂型敌人，死后在附近两路生成1/4血的不可分裂的自身"""

    def __init__(
        self,
        road: int,
        side: Direction,
        speed_factor: float = 1,
        power_factor: float = 1,
        /,
        major: bool = True,
    ) -> None:
        super().__init__(road, side, speed_factor, power_factor)
        self.is_major = major
        shape_factor = 0.4 + major * 0.4
        pygame.draw.circle(
            self.image,
            Cyan,
            (ENEMY_SIZE // 2, ENEMY_SIZE // 2),
            ENEMY_SIZE * shape_factor // 2,
        )
        pygame.draw.circle(
            self.image,
            AlmostBlack,
            (ENEMY_SIZE // 2, ENEMY_SIZE // 2),
            ENEMY_SIZE * shape_factor // 2,
            1,
        )
        self.mask = pygame.mask.from_surface(self.image)
        self.hp = 10 * self.power_factor * (1 if major else 0.25)
        self.worth = 10 if major else 3

    def update(self) -> None:
        super().update()
        if self.hp <= 0:
            super().on_death(self.worth)
            if self.is_major:
                left, right = self.road + 1, self.road - 1
                for road in [left, right]:
                    if road in range(EDGES):
                        splits = self.__class__(
                            road,
                            self.side,
                            self.speed_modifier,
                            self.power_factor,
                            major=False,
                        )
                        if self.side in [Direction.UP, Direction.DOWN]:
                            splits.blink(by_y=True, y=self.pos.y)
                        else:
                            splits.blink(by_x=True, x=self.pos.x)
                        enemy_test.add(splits)
            self.kill()


def recalculate_paths():
    for enemy in enemy_test:
        enemy.path = enemy.calculate_path()
        enemy.path_index = 0
        enemy.reached_goal = False
