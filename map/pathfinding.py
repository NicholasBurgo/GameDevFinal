"""A* pathfinding algorithm for navigating the tile map."""

import heapq

import pygame

from config import CUSTOMER_SOLID_TILES, TILE_DOOR, TILE_FLOOR, TILE_NODE, TILE_SIZE


class Node:
    """Represents a node in the A* pathfinding graph."""

    def __init__(self, col: int, row: int, g: float = 0, h: float = 0, parent: "Node | None" = None):
        self.col = col
        self.row = row
        self.g = g  # Cost from start to this node
        self.h = h  # Heuristic cost from this node to goal
        self.f = g + h  # Total cost
        self.parent = parent

    def __lt__(self, other: "Node") -> bool:
        """For priority queue comparison."""
        return self.f < other.f

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, Node):
            return False
        return self.col == other.col and self.row == other.row

    def __hash__(self) -> int:
        """Hash for set operations."""
        return hash((self.col, self.row))


def heuristic(col1: int, row1: int, col2: int, row2: int) -> float:
    """Manhattan distance heuristic."""
    return abs(col1 - col2) + abs(row1 - row2)


def is_walkable(tile_map, col: int, row: int) -> bool:
    """Check if a tile is walkable for customers."""
    tile = tile_map.tile_at(col, row)
    # Nodes are walkable (customers can stand on them to buy)
    # Doors are also walkable for customers
    return tile == TILE_FLOOR or tile == TILE_NODE or tile == TILE_DOOR or tile not in CUSTOMER_SOLID_TILES


def get_neighbors(tile_map, col: int, row: int) -> list[tuple[int, int]]:
    """Get walkable neighboring tiles (4-directional)."""
    neighbors: list[tuple[int, int]] = []
    for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:  # Up, Down, Right, Left
        new_col = col + dc
        new_row = row + dr
        if is_walkable(tile_map, new_col, new_row):
            neighbors.append((new_col, new_row))
    return neighbors


def world_to_tile(world_pos: pygame.Vector2) -> tuple[int, int]:
    """Convert world coordinates to tile coordinates."""
    col = int(world_pos.x // TILE_SIZE)
    row = int(world_pos.y // TILE_SIZE)
    return col, row


def tile_to_world(col: int, row: int) -> pygame.Vector2:
    """Convert tile coordinates to world coordinates (center of tile)."""
    x = col * TILE_SIZE + TILE_SIZE // 2
    y = row * TILE_SIZE + TILE_SIZE // 2
    return pygame.Vector2(x, y)


def find_path(
    tile_map,
    start: pygame.Vector2,
    goal: pygame.Vector2,
    max_path_length: int = 1000,
) -> list[pygame.Vector2] | None:
    """
    Find a path from start to goal using A* algorithm.
    Returns a list of world-space positions (tile centers) representing the path, or None if no path found.
    """
    start_col, start_row = world_to_tile(start)
    goal_col, goal_row = world_to_tile(goal)

    # Check if start and goal are walkable
    if not is_walkable(tile_map, start_col, start_row):
        # Try to find nearest walkable tile (check in expanding radius)
        found_start = False
        for radius in range(1, 5):  # Check up to 4 tiles away
            for dc in range(-radius, radius + 1):
                for dr in range(-radius, radius + 1):
                    if abs(dc) == radius or abs(dr) == radius:  # Only check perimeter
                        if is_walkable(tile_map, start_col + dc, start_row + dr):
                            start_col += dc
                            start_row += dr
                            found_start = True
                            break
                if found_start:
                    break
            if found_start:
                break
        if not found_start:
            return None  # No walkable tile found near start

    if not is_walkable(tile_map, goal_col, goal_row):
        # Try to find nearest walkable tile (check in expanding radius)
        found_goal = False
        for radius in range(1, 5):  # Check up to 4 tiles away
            for dc in range(-radius, radius + 1):
                for dr in range(-radius, radius + 1):
                    if abs(dc) == radius or abs(dr) == radius:  # Only check perimeter
                        if is_walkable(tile_map, goal_col + dc, goal_row + dr):
                            goal_col += dc
                            goal_row += dr
                            found_goal = True
                            break
                if found_goal:
                    break
            if found_goal:
                break
        if not found_goal:
            return None  # No walkable tile found near goal

    # If start and goal are the same tile, return direct path
    if start_col == goal_col and start_row == goal_row:
        return [tile_to_world(goal_col, goal_row)]

    # Initialize open and closed sets
    open_set: list[Node] = []
    closed_set: set[tuple[int, int]] = set()

    # Create start node
    start_node = Node(start_col, start_row, g=0, h=heuristic(start_col, start_row, goal_col, goal_row))
    heapq.heappush(open_set, start_node)

    # A* main loop
    while open_set:
        current = heapq.heappop(open_set)
        current_pos = (current.col, current.row)

        # Skip if already processed
        if current_pos in closed_set:
            continue

        closed_set.add(current_pos)

        # Check if we reached the goal
        if current.col == goal_col and current.row == goal_row:
            # Reconstruct path
            path: list[pygame.Vector2] = []
            node: Node | None = current
            path_length = 0
            while node is not None:
                path.append(tile_to_world(node.col, node.row))
                node = node.parent
                path_length += 1
                if path_length > max_path_length:
                    return None  # Path too long, probably stuck
            path.reverse()
            return path

        # Check neighbors
        for neighbor_col, neighbor_row in get_neighbors(tile_map, current.col, current.row):
            neighbor_pos = (neighbor_col, neighbor_row)

            # Skip if already in closed set
            if neighbor_pos in closed_set:
                continue

            # Calculate costs
            g_cost = current.g + 1.0
            h_cost = heuristic(neighbor_col, neighbor_row, goal_col, goal_row)
            f_cost = g_cost + h_cost

            # Check if this neighbor is already in open set with better cost
            found_better = False
            for open_node in open_set:
                if open_node.col == neighbor_col and open_node.row == neighbor_row:
                    if open_node.f <= f_cost:
                        found_better = True
                    break

            if not found_better:
                neighbor_node = Node(neighbor_col, neighbor_row, g_cost, h_cost, current)
                heapq.heappush(open_set, neighbor_node)

    # No path found
    return None
