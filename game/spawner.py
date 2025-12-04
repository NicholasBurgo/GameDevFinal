"""Customer spawning logic."""

import random
from typing import Union

import pygame

from entities import Customer, LitterCustomer, ThiefCustomer


class CustomerSpawner:
    """Manages customer spawning."""

    def __init__(
        self,
        door_pos: pygame.Vector2,
        shelf_targets: list[pygame.Vector2],
        counter_targets: list[pygame.Vector2],
        shelf_browsing_positions: dict[tuple[float, float], list[pygame.Vector2]] | None = None,
        tile_map=None,
        node_targets: list[pygame.Vector2] = None,
        min_spawn_delay: float = 1.0,
        max_spawn_delay: float = 3.0,
    ) -> None:
        self.door_pos = door_pos
        self.shelf_targets = shelf_targets
        self.counter_targets = counter_targets
        self.shelf_browsing_positions = shelf_browsing_positions
        self.tile_map = tile_map
        self.node_targets = node_targets or []
        self.min_spawn_delay = min_spawn_delay
        self.max_spawn_delay = max_spawn_delay
        
        self.spawn_timer = 0.0
        self.next_spawn_in = random.uniform(min_spawn_delay, max_spawn_delay)

    def update(self, dt: float, customers: list[Union[Customer, ThiefCustomer, LitterCustomer]]) -> Union[Customer, ThiefCustomer, LitterCustomer] | None:
        """
        Update spawner and return a new customer if one should spawn, None otherwise.
        Allows up to 3 customers at a time with staggered spawning.
        Randomly chooses customer type: 70% regular, 15% thief, 15% litter.
        """
        MAX_CUSTOMERS = 3
        
        # Only spawn if we have fewer than max customers
        if len(customers) < MAX_CUSTOMERS:
            self.spawn_timer += dt
            if self.spawn_timer >= self.next_spawn_in:
                self.spawn_timer = 0.0
                # Staggered spawning: longer delay when more customers present
                delay_multiplier = 1.0 + (len(customers) * 0.5)  # Increase delay based on customer count
                self.next_spawn_in = random.uniform(self.min_spawn_delay, self.max_spawn_delay) * delay_multiplier
                
                # Randomly choose customer type: 70% regular, 15% thief, 15% litter
                rand = random.random()
                if rand < 0.70:
                    # Regular customer
                    return Customer(self.door_pos, self.shelf_targets, self.counter_targets, self.shelf_browsing_positions, self.tile_map, self.node_targets)
                elif rand < 0.85:
                    # Thief customer
                    return ThiefCustomer(self.door_pos, self.shelf_targets, self.counter_targets, self.shelf_browsing_positions, self.tile_map, self.node_targets)
                else:
                    # Litter customer
                    return LitterCustomer(self.door_pos, self.shelf_targets, self.counter_targets, self.shelf_browsing_positions, self.tile_map, self.node_targets)
        return None

