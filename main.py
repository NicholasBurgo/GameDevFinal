"""Main entry point for the game."""

import sys

import pygame

from config import FPS, TILE_SIZE
from game import GameState
from map import TileMap
from rendering import HUD, Renderer


def main() -> None:
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Pygame Store - Tile World")
    
    # Create tile map
    tile_map = TileMap()
    
    # Screen size derived from map dimensions so the whole store fits exactly.
    screen_width = tile_map.cols * TILE_SIZE
    screen_height = tile_map.rows * TILE_SIZE
    
    screen = pygame.display.set_mode((screen_width, screen_height))
    clock = pygame.time.Clock()

    # Initialize game systems
    game_state = GameState(tile_map)
    renderer = Renderer(screen)
    hud = HUD()

    # HUD text
    hud_lines = [
        "Use WASD or arrow keys to move.",
        "ESC or window close to quit.",
        "Customers enter, shop, pay, and leave.",
    ]

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0

        # Handle events
        for event in pygame.event.get():
            if game_state.handle_event(event):
                running = False

        # Update game state
        game_state.update(dt)

        # Render everything
        renderer.clear()
        renderer.draw_map(tile_map)
        renderer.draw_entities(
            game_state.player,
            game_state.customers,
            game_state.cash_items,
        )
        hud.draw(screen, hud_lines)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
