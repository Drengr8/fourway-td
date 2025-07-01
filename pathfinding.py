import heapq
from typing import List, Tuple, Optional

def astar_pathfinding(navigation_map: List[List[bool]], start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
    """
    A* pathfinding for a 2D grid.
    navigation_map: 2D list of bools (True=walkable, False=blocked)
    start, goal: (x, y) tuples
    Returns: list of (x, y) tuples from start to goal, or None if no path.
    """
    edges = len(navigation_map)
    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_set = []
    heapq.heappush(open_set, (0 + heuristic(start, goal), 0, start, [start]))
    closed_set = set()

    while open_set:
        est_total, cost, current, path = heapq.heappop(open_set)
        if current == goal:
            return path
        if current in closed_set:
            continue
        closed_set.add(current)
        x, y = current
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < edges and 0 <= ny < edges and navigation_map[nx][ny]:
                neighbor = (nx, ny)
                if neighbor in closed_set:
                    continue
                heapq.heappush(open_set, (cost + 1 + heuristic(neighbor, goal), cost + 1, neighbor, path + [neighbor]))
    return None 