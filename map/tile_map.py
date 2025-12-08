"""Tile map system."""

import pygame

from config import (
    COLOR_COMPUTER,
    COLOR_COUNTER,
    COLOR_DOOR,
    COLOR_FLOOR,
    COLOR_NODE,
    COLOR_OFFICE_DOOR,
    COLOR_SHELF,
    COLOR_WALL,
    TILE_ACTIVATION,
    TILE_ACTIVATION_1,
    TILE_ACTIVATION_2,
    TILE_ACTIVATION_3,
    TILE_COMPUTER,
    TILE_COUNTER,
    TILE_DOOR,
    TILE_FLOOR,
    TILE_NODE,
    TILE_OFFICE_DOOR,
    TILE_SHELF,
    TILE_SIZE,
    TILE_WALL,
)


# Simple retro-style store: outer walls, some shelves forming aisles.
STORE_MAP = [
    "################O###",
    "#..................#",
    "#...N.......CCCCC..#",
    "#.SSSS........N....#",
    "#..................#",
    "#...N..............D",
    "#.SSSS....SSSS.....#",
    "#...........N......#",
    "#....N......N......#",
    "#.SSSS....SSSS.....#",
    "#..................#",
    "####################",
]

# Office room map - smaller room for the player
OFFICE_MAP = [
    "############",
    "#P...P...P.#",
    "#1...2...3.#",
    "#..........#",
    "#..........#",
    "#..........#",
    "#..........#",  
    "###O########",
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

    def draw(self, surface: pygame.Surface, shelf_texture: pygame.Surface | None = None, wall_stone_texture: pygame.Surface | None = None, 
             counter_texture: pygame.Surface | None = None) -> None:
        """Draw the map to the surface."""
        for row in range(self.rows):
            for col in range(self.cols):
                tile = self.map_data[row][col]

                x = col * TILE_SIZE
                y = row * TILE_SIZE
                rect = pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)

                if tile == TILE_WALL:
                    # Use blue stone texture if available, otherwise fall back to color
                    if wall_stone_texture is not None:
                        surface.blit(wall_stone_texture, rect)
                    else:
                        color = COLOR_WALL
                        pygame.draw.rect(surface, color, rect)
                elif tile == TILE_SHELF:
                    # Use shelf texture if available, otherwise fall back to color
                    if shelf_texture is not None:
                        surface.blit(shelf_texture, rect)
                    else:
                        color = COLOR_SHELF
                        pygame.draw.rect(surface, color, rect)
                elif tile == TILE_DOOR:
                    color = COLOR_DOOR
                    pygame.draw.rect(surface, color, rect)
                elif tile == TILE_OFFICE_DOOR:
                    color = COLOR_OFFICE_DOOR
                    pygame.draw.rect(surface, color, rect)
                elif tile == TILE_COUNTER:
                    # Use counter texture if available, otherwise fall back to color
                    if counter_texture is not None:
                        surface.blit(counter_texture, rect)
                    else:
                        color = COLOR_COUNTER
                        pygame.draw.rect(surface, color, rect)
                elif tile == TILE_NODE:
                    # Nodes are invisible - render as floor
                    color = COLOR_FLOOR
                    pygame.draw.rect(surface, color, rect)
                elif tile == TILE_COMPUTER:
                    # Determine which computer to draw based on column
                    comp_idx = -1
                    if col == 1: comp_idx = 0
                    elif col == 5: comp_idx = 1
                    elif col == 9: comp_idx = 2
                    
                    if computer_images and 0 <= comp_idx < len(computer_images) and computer_images[comp_idx]:
                        surface.blit(computer_images[comp_idx], rect)
                    else:
                        color = COLOR_COMPUTER
                        pygame.draw.rect(surface, color, rect)
                elif tile in [TILE_ACTIVATION, TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3]:
                    # Activation tiles are same color as floor (invisible)
                    color = COLOR_FLOOR
                    pygame.draw.rect(surface, color, rect)
                else:
                    color = COLOR_FLOOR
                    pygame.draw.rect(surface, color, rect)

