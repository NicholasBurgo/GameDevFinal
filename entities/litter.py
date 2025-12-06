"""Litter entity."""

import pygame

from config import COLOR_LITTER, TILE_SIZE


class Litter:
    def __init__(self, pos: pygame.Vector2) -> None:
        self.pos = pygame.Vector2(pos)

    def draw(self, surface: pygame.Surface) -> None:
        size = TILE_SIZE // 4
        rect = pygame.Rect(
            int(self.pos.x - size / 2),
            int(self.pos.y - size / 2),
            size,
            size,
        )
        pygame.draw.rect(surface, COLOR_LITTER, rect)






