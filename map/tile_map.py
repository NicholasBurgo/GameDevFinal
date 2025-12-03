"""Tile map system."""

import pygame

from config import (
    COLOR_COUNTER,
    COLOR_DOOR,
    COLOR_FLOOR,
    COLOR_SHELF,
    COLOR_WALL,
    TILE_COUNTER,
    TILE_DOOR,
    TILE_FLOOR,
    TILE_SHELF,
    TILE_SIZE,
    TILE_WALL,
)


# Simple retro-style store: outer walls, some shelves forming aisles.
STORE_MAP = [
    "####################",
    "#..................#",
    "#...........CCCCC..#",
    "#.SSSS.............#",
    "#..................#",
    "#..................D",
    "#.SSSS....SSSS.....#",
    "#..................#",
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
                else:
                    color = COLOR_FLOOR

                pygame.draw.rect(surface, color, rect)

