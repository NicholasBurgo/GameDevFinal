"""Customer spawning logic."""

import random

import pygame

from entities import Customer


class CustomerSpawner:
    """Manages customer spawning."""

    def __init__(
        self,
        door_pos: pygame.Vector2,
        shelf_targets: list[pygame.Vector2],
        counter_targets: list[pygame.Vector2],
        min_spawn_delay: float = 1.0,
        max_spawn_delay: float = 3.0,
    ) -> None:
        self.door_pos = door_pos
        self.shelf_targets = shelf_targets
        self.counter_targets = counter_targets
        self.min_spawn_delay = min_spawn_delay
        self.max_spawn_delay = max_spawn_delay
        
        self.spawn_timer = 0.0
        self.next_spawn_in = random.uniform(min_spawn_delay, max_spawn_delay)

    def update(self, dt: float, customers: list[Customer]) -> Customer | None:
        """
        Update spawner and return a new customer if one should spawn, None otherwise.
        Only spawns when there are no customers inside.
        """
        if not customers:
            self.spawn_timer += dt
            if self.spawn_timer >= self.next_spawn_in:
                self.spawn_timer = 0.0
                self.next_spawn_in = random.uniform(self.min_spawn_delay, self.max_spawn_delay)
                return Customer(self.door_pos, self.shelf_targets, self.counter_targets)
        return None

