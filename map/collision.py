"""Collision detection functions."""

import pygame

from config import CUSTOMER_SOLID_TILES, SOLID_TILES, TILE_DOOR, TILE_SIZE


def get_solid_tiles_around(rect: pygame.Rect, tile_map) -> list[pygame.Rect]:
    """Return solid tile rects near the given rect to test collisions against."""
    tiles: list[pygame.Rect] = []

    left = max(rect.left // TILE_SIZE - 1, 0)
    right = min(rect.right // TILE_SIZE + 1, tile_map.cols - 1)
    top = max(rect.top // TILE_SIZE - 1, 0)
    bottom = min(rect.bottom // TILE_SIZE + 1, tile_map.rows - 1)

    for row in range(top, bottom + 1):
        for col in range(left, right + 1):
            if tile_map.tile_at(col, row) in SOLID_TILES:
                x = col * TILE_SIZE
                y = row * TILE_SIZE
                tiles.append(pygame.Rect(x, y, TILE_SIZE, TILE_SIZE))

    return tiles


def get_customer_solid_tiles_around(rect: pygame.Rect, tile_map) -> tuple[list[pygame.Rect], list[pygame.Rect]]:
    """
    Return solid tile rects for customers.
    Returns (obstacle_rects, door_rects) so doors can be handled with extra phasing.
    """
    obstacle_tiles: list[pygame.Rect] = []
    door_tiles: list[pygame.Rect] = []

    left = max(rect.left // TILE_SIZE - 1, 0)
    right = min(rect.right // TILE_SIZE + 1, tile_map.cols - 1)
    top = max(rect.top // TILE_SIZE - 1, 0)
    bottom = min(rect.bottom // TILE_SIZE + 1, tile_map.rows - 1)

    for row in range(top, bottom + 1):
        for col in range(left, right + 1):
            tile = tile_map.tile_at(col, row)
            x = col * TILE_SIZE
            y = row * TILE_SIZE
            tile_rect = pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)
            
            if tile == TILE_DOOR:
                door_tiles.append(tile_rect)
            elif tile in CUSTOMER_SOLID_TILES:
                obstacle_tiles.append(tile_rect)

    return (obstacle_tiles, door_tiles)

