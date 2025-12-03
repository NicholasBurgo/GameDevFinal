"""Main game state management."""

import pygame

from config import COLOR_PLAYER, PLAYER_RADIUS, TILE_SIZE
from entities import Cash, Customer, Player
from map import TileMap, get_customer_solid_tiles_around, get_solid_tiles_around
from .spawner import CustomerSpawner


class GameState:
    """Manages the main game state and game loop logic."""

    def __init__(self, tile_map: TileMap) -> None:
        self.tile_map = tile_map
        
        # Precompute important tile positions for customers
        door_centers = tile_map.find_tile_centers("D")  # TILE_DOOR
        shelf_centers = tile_map.find_tile_centers("S")  # TILE_SHELF
        counter_centers = tile_map.find_tile_centers("C")  # TILE_COUNTER

        door_pos = door_centers[0] if door_centers else pygame.Vector2(
            tile_map.cols * TILE_SIZE // 2, 
            tile_map.rows * TILE_SIZE // 2
        )

        # Initialize spawner
        self.spawner = CustomerSpawner(door_pos, shelf_centers, counter_centers)

        # Game entities
        self.customers: list[Customer] = []
        self.cash_items: list[Cash] = []

        # Start roughly in the middle of the store on a floor tile
        start_col = 1
        start_row = 1
        start_x = start_col * TILE_SIZE + TILE_SIZE // 2
        start_y = start_row * TILE_SIZE + TILE_SIZE // 2

        self.player = Player(start_x, start_y, PLAYER_RADIUS, COLOR_PLAYER)

    def update(self, dt: float) -> None:
        """Update game state."""
        # Handle player input and movement
        direction = self.player.handle_input()
        solid_rects = get_solid_tiles_around(self.player.rect, self.tile_map)
        self.player.move_and_collide(direction, solid_rects)

        # Spawn customers
        new_customer = self.spawner.update(dt, self.customers)
        if new_customer:
            self.customers.append(new_customer)

        # Update customers
        for customer in self.customers:
            customer_solid_rects = get_customer_solid_tiles_around(customer.rect, self.tile_map)
            customer.update(dt, customer_solid_rects)
            if customer.drop_cash:
                # Place cash at the shelf position where customer is standing
                self.cash_items.append(Cash(customer.position))
                customer.drop_cash = False

        # Remove customers that have left
        self.customers = [c for c in self.customers if not c.finished]

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Handle pygame events. Returns True if event was handled and should stop propagation.
        """
        if event.type == pygame.QUIT:
            return True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return True
        return False

