"""Tile map system."""

import pygame

from config import (
    COLOR_COUNTER,
    COLOR_DOOR,
    COLOR_FLOOR,
    COLOR_NODE,
    COLOR_SHELF,
    COLOR_WALL,
    TILE_COUNTER,
    TILE_DOOR,
    TILE_FLOOR,
    TILE_NODE,
    TILE_SHELF,
    TILE_SIZE,
    TILE_WALL,
)


# Simple retro-style store: outer walls, some shelves forming aisles.
STORE_MAP = [
    "####################",
    "#..................#",
    "#...N.......CCCCC..#",
    "#.SSSS........N....#",
    "#..................#",
    "#...N..............D",
    "#.SSSS....SSSS.....#",
    "#...........N......#",
    "#..................#",
    "####################",
]


class TileMap:
    """Manages the tile-based map."""

    def __init__(self, map_data: list[str] | None = None) -> None:
        self.map_data = map_data or STORE_MAP
        self.rows = len(self.map_data)
        self.cols = len(self.map_data[0]) if self.map_data else 0

    def tile_at(self, col: int, row: int) -> str:
        """Get tile code at given column and row."""
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self.map_data[row][col]
        return TILE_WALL  # Treat out-of-bounds as solid wall

    def find_tile_centers(self, tile_code: str) -> list[pygame.Vector2]:
        """Return world-space centers of all tiles of a given type."""
        centers: list[pygame.Vector2] = []
        for row in range(self.rows):
            for col in range(self.cols):
                if self.map_data[row][col] == tile_code:
                    x = col * TILE_SIZE + TILE_SIZE // 2
                    y = row * TILE_SIZE + TILE_SIZE // 2
                    centers.append(pygame.Vector2(x, y))
        return centers

    def find_floor_tiles_around_shelf_group(self, shelf_group_center: pygame.Vector2, search_radius: int = 2) -> list[pygame.Vector2]:
        """
        Find floor tiles around a shelf group center that customers can walk on.
        Returns list of world-space centers of valid floor tiles.
        """
        valid_positions: list[pygame.Vector2] = []
        
        # Convert world position to tile coordinates
        center_col = int(shelf_group_center.x // TILE_SIZE)
        center_row = int(shelf_group_center.y // TILE_SIZE)
        
        # Search in a radius around the shelf center
        for row_offset in range(-search_radius, search_radius + 1):
            for col_offset in range(-search_radius, search_radius + 1):
                row = center_row + row_offset
                col = center_col + col_offset
                
                # Check if tile is a floor tile
                if self.tile_at(col, row) == TILE_FLOOR:
                    x = col * TILE_SIZE + TILE_SIZE // 2
                    y = row * TILE_SIZE + TILE_SIZE // 2
                    valid_positions.append(pygame.Vector2(x, y))
        
        return valid_positions

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the map to the surface."""
        for row in range(self.rows):
            for col in range(self.cols):
                tile = self.map_data[row][col]

                x = col * TILE_SIZE
                y = row * TILE_SIZE
                rect = pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)

                if tile == TILE_WALL:
                    color = COLOR_WALL
                elif tile == TILE_SHELF:
                    color = COLOR_SHELF
                elif tile == TILE_DOOR:
                    color = COLOR_DOOR
                elif tile == TILE_COUNTER:
                    color = COLOR_COUNTER
                elif tile == TILE_NODE:
                    # Nodes are invisible - render as floor
                    color = COLOR_FLOOR
                else:
                    color = COLOR_FLOOR

                pygame.draw.rect(surface, color, rect)

