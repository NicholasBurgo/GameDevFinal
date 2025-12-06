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
        min_spawn_delay: float = 0.5,
        max_spawn_delay: float = 4.0,
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
        # Random initial delay to prevent all customers spawning at once
        self.next_spawn_in = random.uniform(min_spawn_delay, max_spawn_delay)

    def update(self, dt: float, customers: list[Union[Customer, ThiefCustomer, LitterCustomer]]) -> Union[Customer, ThiefCustomer, LitterCustomer] | None:
        """
        Update spawner and return a new customer if one should spawn, None otherwise.
        Allows up to 6 customers at a time with randomized spawning.
        Randomly chooses customer type: 70% regular, 15% thief, 15% litter.
        """
        MAX_CUSTOMERS = 6
        
        # Only spawn if we have fewer than max customers
        if len(customers) < MAX_CUSTOMERS:
            self.spawn_timer += dt
            if self.spawn_timer >= self.next_spawn_in:
                self.spawn_timer = 0.0
                # Random spawn delay - wider range for more variation
                # Slightly longer delay when more customers present to prevent clustering
                base_delay = random.uniform(self.min_spawn_delay, self.max_spawn_delay)
                if len(customers) >= 3:
                    # If we already have 3+ customers, add some extra delay
                    base_delay *= random.uniform(1.2, 1.5)
                self.next_spawn_in = base_delay
                
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

