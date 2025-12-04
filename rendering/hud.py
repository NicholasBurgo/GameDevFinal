"""HUD/UI rendering."""

import pygame

from config import COLOR_TEXT


class HUD:
    """Handles HUD and UI rendering."""

    def __init__(self, font: pygame.font.Font | None = None) -> None:
        self.font = font or pygame.font.SysFont(None, 22)

    def draw(self, surface: pygame.Surface, lines: list[str]) -> None:
        """Draw HUD text lines."""
        y = 5
        for line in lines:
            surf = self.font.render(line, True, COLOR_TEXT)
            surface.blit(surf, (5, y))
            y += surf.get_height() + 2






