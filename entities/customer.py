"""Customer entity with AI behavior."""

import math
import random

import pygame

from config import COLOR_CUSTOMER, CUSTOMER_RADIUS, CUSTOMER_SPEED, FPS, TILE_SIZE


class Customer:
    """Simple customer AI: enter door -> go to shelf -> browse around shelf -> drop cash -> leave."""

    def __init__(
        self,
        door_pos: pygame.Vector2,
        shelf_targets: list[pygame.Vector2],
        counter_targets: list[pygame.Vector2] = None,  # Kept for compatibility but not used
    ) -> None:
        # Spawn just outside the door, to the right
        self.position = pygame.Vector2(door_pos.x + TILE_SIZE * 0.75, door_pos.y)
        self.radius = CUSTOMER_RADIUS
        self.color = COLOR_CUSTOMER

        self.door_pos = pygame.Vector2(door_pos)
        self.shelf_targets = shelf_targets or [self.door_pos]

        self.state = "entering"
        self.target = pygame.Vector2(self.door_pos)

        # Choose a random shelf
        self.shelf_pos = random.choice(self.shelf_targets)

        # Browsing around shelf
        self.browsing_time = random.uniform(3.0, 8.0)  # Total time to browse
        self.browsing_elapsed = 0.0
        self.browsing_target: pygame.Vector2 | None = None
        self.browsing_radius = TILE_SIZE * 1.5  # How far around the shelf to walk

        # Leaving target (outside the door to the right)
        self.leave_pos = pygame.Vector2(self.door_pos.x + TILE_SIZE * 2.0, self.door_pos.y)

        self.finished = False
        self.drop_cash = False

    @property
    def rect(self) -> pygame.Rect:
        """Axis-aligned bounding box approximating the circular customer."""
        return pygame.Rect(
            int(self.position.x - self.radius),
            int(self.position.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def update(self, dt: float, solid_rects: list[pygame.Rect]) -> None:
        if self.state == "entering":
            if self._move_towards(self.door_pos, dt, solid_rects, proximity_threshold=TILE_SIZE * 0.3):
                self.state = "to_shelf"
        elif self.state == "to_shelf":
            # Check if close enough to shelf (within 1 tile radius) - stand around it, not in it
            distance_to_shelf = (self.position - self.shelf_pos).length()
            if distance_to_shelf <= TILE_SIZE * 1.0:
                self.state = "browsing"
                self.browsing_elapsed = 0.0
                self._pick_new_browsing_target()
            else:
                self._move_towards(self.shelf_pos, dt, solid_rects, proximity_threshold=TILE_SIZE * 1.0)
        elif self.state == "browsing":
            self.browsing_elapsed += dt
            
            # If we've browsed long enough, drop cash and leave
            if self.browsing_elapsed >= self.browsing_time:
                self.drop_cash = True
                self.state = "leaving"
            else:
                # Walk around the shelf - pick new positions to walk to
                if self.browsing_target is None:
                    self._pick_new_browsing_target()
                else:
                    # Move towards browsing target
                    if self._move_towards(self.browsing_target, dt, solid_rects, proximity_threshold=TILE_SIZE * 0.4):
                        # Reached browsing target, pick a new one
                        self._pick_new_browsing_target()
        elif self.state == "leaving":
            if self._move_towards(self.leave_pos, dt, solid_rects, proximity_threshold=TILE_SIZE * 0.3):
                self.finished = True

    def _pick_new_browsing_target(self) -> None:
        """Pick a random position around the shelf to walk to while browsing."""
        # Pick a random angle and distance around the shelf
        angle = random.uniform(0, 2 * math.pi)  # Random angle in radians
        distance = random.uniform(TILE_SIZE * 0.8, self.browsing_radius)
        
        # Calculate position around the shelf using trigonometry
        offset_x = distance * math.cos(angle)
        offset_y = distance * math.sin(angle)
        
        self.browsing_target = pygame.Vector2(
            self.shelf_pos.x + offset_x,
            self.shelf_pos.y + offset_y
        )

    def _move_towards(self, target: pygame.Vector2, dt: float, solid_rects: list[pygame.Rect], proximity_threshold: float = TILE_SIZE * 0.3) -> bool:
        """Move towards target with collision detection. Returns True when within proximity_threshold."""
        direction = target - self.position
        distance = direction.length()
        
        # Check if we're close enough to the target
        if distance < proximity_threshold:
            return True

        if distance < 1e-3:
            self.position.update(target)
            return True

        direction.normalize_ip()
        # Move per-frame like the player (multiply by FPS to convert from per-second to per-frame)
        step = CUSTOMER_SPEED * dt * FPS
        
        # Try moving on X axis first
        old_x = self.position.x
        self.position.x += direction.x * step
        customer_rect = self.rect
        for tile_rect in solid_rects:
            if customer_rect.colliderect(tile_rect):
                # Hit an obstacle - stop movement
                self.position.x = old_x
                break
        
        # Then move on Y axis
        old_y = self.position.y
        self.position.y += direction.y * step
        customer_rect = self.rect
        for tile_rect in solid_rects:
            if customer_rect.colliderect(tile_rect):
                # Hit an obstacle - stop movement
                self.position.y = old_y
                break
        
        # Check if we're now close enough to the target after movement
        new_distance = (target - self.position).length()
        if new_distance < proximity_threshold:
            return True
        
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(
            surface,
            self.color,
            (int(self.position.x), int(self.position.y)),
            self.radius,
        )

