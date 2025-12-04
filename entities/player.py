"""Player entity."""

import pygame

from config import PLAYER_SPEED


class Player:
    def __init__(self, x: float, y: float, radius: int, color: tuple[int, int, int]) -> None:
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color
        self.speed = PLAYER_SPEED

    @property
    def rect(self) -> pygame.Rect:
        """Axis-aligned bounding box approximating the circular player."""
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def handle_input(self) -> pygame.Vector2:
        keys = pygame.key.get_pressed()

        dx = 0
        dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1

        direction = pygame.Vector2(dx, dy)
        if direction.length_squared() > 0:
            direction = direction.normalize()
        return direction

    def move_and_collide(self, direction: pygame.Vector2, solids_rects: list[pygame.Rect]) -> None:
        # Move on X axis
        self.x += direction.x * self.speed
        player_rect = self.rect
        for tile_rect in solids_rects:
            if player_rect.colliderect(tile_rect):
                if direction.x > 0:  # moving right
                    # place player just to the left of the tile
                    self.x = tile_rect.left - self.radius
                elif direction.x < 0:  # moving left
                    # place player just to the right of the tile
                    self.x = tile_rect.right + self.radius
                player_rect = self.rect

        # Move on Y axis
        self.y += direction.y * self.speed
        player_rect = self.rect
        for tile_rect in solids_rects:
            if player_rect.colliderect(tile_rect):
                if direction.y > 0:  # moving down
                    # place player just above the tile
                    self.y = tile_rect.top - self.radius
                elif direction.y < 0:  # moving up
                    # place player just below the tile
                    self.y = tile_rect.bottom + self.radius
                player_rect = self.rect

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)




