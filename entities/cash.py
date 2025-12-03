"""Cash entity."""

import pygame

from config import COLOR_CASH, TILE_SIZE


class Cash:
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
        pygame.draw.rect(surface, COLOR_CASH, rect)

