"""Main renderer for game entities and map."""

import pygame

from config import COLOR_BG
from entities import Cash, Customer, Player
from map import TileMap


class Renderer:
    """Handles all drawing operations."""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen

    def clear(self) -> None:
        """Clear the screen with background color."""
        self.screen.fill(COLOR_BG)

    def draw_map(self, tile_map: TileMap) -> None:
        """Draw the tile map."""
        tile_map.draw(self.screen)

    def draw_entities(
        self,
        player: Player,
        customers: list[Customer],
        cash_items: list[Cash],
    ) -> None:
        """Draw all game entities."""
        # Draw cash and customers
        for cash in cash_items:
            cash.draw(self.screen)
        for customer in customers:
            customer.draw(self.screen)

        # Draw player last so it appears on top
        player.draw(self.screen)

