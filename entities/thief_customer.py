"""Thief customer entity that steals dodge coins and leaves."""

import math
import random

import pygame

from config import CUSTOMER_RADIUS, CUSTOMER_SPEED, FPS, TILE_SIZE, generate_random_customer_color
from entities.cash import Cash
from map import find_path


class ThiefCustomer:
    """Thief customer AI: enter door -> browse like customer -> find dodge coin -> steal one dodge coin -> leave."""

    def __init__(
        self,
        door_pos: pygame.Vector2,
        shelf_targets: list[pygame.Vector2],
        counter_targets: list[pygame.Vector2] = None,  # Kept for compatibility but not used
        shelf_browsing_positions: dict[tuple[float, float], list[pygame.Vector2]] | None = None,
        tile_map=None,  # Tile map for pathfinding
        node_targets: list[pygame.Vector2] = None,  # Node positions customers can buy from
    ) -> None:
        # Spawn at the door position
        self.position = pygame.Vector2(door_pos)
        self.radius = CUSTOMER_RADIUS
        self.color = generate_random_customer_color()
        
        # Health system
        self.max_health = 3
        self.health = 3
        self.show_health_bar = False
        
        # Knockback system
        self.knockback_velocity = pygame.Vector2(0, 0)
        self.knockback_timer = 0.0

        self.door_pos = pygame.Vector2(door_pos)
        self.shelf_targets = shelf_targets or [self.door_pos]
        self.node_targets = node_targets or []
        self.tile_map = tile_map

        self.state = "entering"
        self.target = pygame.Vector2(self.door_pos)

        # Choose a random target: either a shelf or a node (50/50 chance if nodes exist)
        all_targets = self.shelf_targets + self.node_targets
        if not all_targets:
            all_targets = [self.door_pos]
        
        chosen_target = random.choice(all_targets)
        
        # Determine if it's a shelf or node
        if chosen_target in self.node_targets:
            self.target_type = "node"
            self.node_pos = chosen_target
            self.shelf_pos = None
        else:
            self.target_type = "shelf"
            self.shelf_pos = chosen_target
            self.node_pos = None
        
        # Get valid browsing positions for this shelf (floor tiles around it)
        self.browsing_positions: list[pygame.Vector2] = []
        if self.target_type == "shelf" and self.shelf_pos and shelf_browsing_positions:
            # Use tuple key for dictionary lookup
            shelf_key = (self.shelf_pos.x, self.shelf_pos.y)
            if shelf_key in shelf_browsing_positions:
                self.browsing_positions = shelf_browsing_positions[shelf_key]
        
        # Browsing around shelf first (like regular customer)
        self.browsing_time = random.uniform(2.0, 5.0)  # Browse for a bit before stealing
        self.browsing_elapsed = 0.0
        self.browsing_target: pygame.Vector2 | None = None
        self.shelf_target: pygame.Vector2 | None = None  # Target position to reach shelf area
        
        # Target dodge coin to steal
        self.target_cash: Cash | None = None
        self.target_cash_pos: pygame.Vector2 | None = None

        # A* pathfinding
        self.path: list[pygame.Vector2] | None = None
        self.path_index: int = 0
        self._last_path_recompute_pos: pygame.Vector2 | None = None
        self._stuck_timer: float = 0.0
        self._last_position: pygame.Vector2 = pygame.Vector2(self.position)

        # Leaving target (outside the door to the right)
        self.leave_pos = pygame.Vector2(self.door_pos.x + TILE_SIZE * 2.0, self.door_pos.y)

        # Human-like behavior for nodes
        self.look_around_timer: float = 0.0
        self.look_around_delay: float = random.uniform(0.5, 2.0)
        self.pause_timer: float = 0.0
        self.is_paused: bool = False
        self.approaching_node: bool = False

        self.finished = False
        self.stole_cash = False  # Flag to indicate dodge coin was stolen

    @property
    def rect(self) -> pygame.Rect:
        """Axis-aligned bounding box approximating the circular customer."""
        return pygame.Rect(
            int(self.position.x - self.radius),
            int(self.position.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )
    
    @property
    def is_alive(self) -> bool:
        """Check if customer is alive."""
        return self.health > 0
    
    def take_damage(self, amount: int) -> bool:
        """
        Apply damage to customer. Returns True if customer dies.
        
        Args:
            amount: Damage amount to apply
            
        Returns:
            True if customer dies (health <= 0), False otherwise
        """
        self.health -= amount
        self.show_health_bar = True
        if self.health <= 0:
            self.health = 0
            return True
        return False
    
    def apply_knockback(self, direction: pygame.Vector2, force: float) -> None:
        """
        Apply knockback to customer.
        
        Args:
            direction: Knockback direction (will be normalized)
            force: Knockback force (distance to knock back)
        """
        if direction.length_squared() > 0:
            direction = direction.normalize()
            self.knockback_velocity = direction * force
            self.knockback_timer = 0.3  # Knockback duration in seconds

    def update(self, dt: float, solid_rects: list[pygame.Rect], cash_items: list[Cash], door_rects: list[pygame.Rect] = None, use_player_speed: bool = False) -> None:
        """Update thief behavior. Needs access to dodge coins to find targets."""
        if door_rects is None:
            door_rects = []
        
        # Check if customer is dead
        if not self.is_alive:
            self.finished = True
            return
        
        # Apply knockback first
        if self.knockback_timer > 0.0:
            knockback_distance = self.knockback_velocity.length() * dt * FPS
            if knockback_distance > 0:
                knockback_direction = self.knockback_velocity.normalize() if self.knockback_velocity.length_squared() > 0 else pygame.Vector2(0, 0)
                knockback_move = knockback_direction * knockback_distance
                
                # Try to move with knockback, checking collisions
                test_pos = self.position + knockback_move
                test_rect = pygame.Rect(
                    int(test_pos.x - self.radius),
                    int(test_pos.y - self.radius),
                    self.radius * 2,
                    self.radius * 2,
                )
                
                # Check collision with solid tiles
                collision = False
                for tile_rect in solid_rects:
                    if test_rect.colliderect(tile_rect):
                        collision = True
                        break
                
                if not collision:
                    self.position = test_pos
                # If collision, stop knockback
                else:
                    self.knockback_velocity = pygame.Vector2(0, 0)
                    self.knockback_timer = 0.0
            
            # Decay knockback over time
            self.knockback_timer -= dt
            if self.knockback_timer <= 0.0:
                self.knockback_velocity = pygame.Vector2(0, 0)
                self.knockback_timer = 0.0
            else:
                # Reduce knockback velocity over time
                decay_rate = 0.9  # Reduce by 10% per frame
                self.knockback_velocity *= decay_rate
        
        if self.state == "entering":
            # Allow corner cutting when entering
            if self._move_towards(self.door_pos, dt, solid_rects, proximity_threshold=TILE_SIZE * 0.3, door_rects=door_rects, allow_corner_cutting=True):
                if self.target_type == "node":
                    # Going to a node - go directly to it
                    self.state = "to_node"
                    self._compute_path(self.node_pos)
                else:
                    # Going to a shelf
                    self.state = "to_shelf"
                    # Pick a valid browsing position to go to (not the shelf center!)
                    if self.browsing_positions:
                        self.shelf_target = random.choice(self.browsing_positions)
                    else:
                        # Fallback: use shelf center if no browsing positions available
                        self.shelf_target = self.shelf_pos
                    # Compute path using A*
                    self._compute_path(self.shelf_target)
        
        elif self.state == "to_node":
            # Move towards the node with human-like behavior (thief is more cautious)
            if self.node_pos is None:
                self.state = "leaving"
                self._compute_path(self.leave_pos)
            else:
                distance_to_node = (self.position - self.node_pos).length()
                
                # Thief looks around more when approaching
                if distance_to_node < TILE_SIZE * 2.5:
                    self.approaching_node = True
                    self.look_around_timer += dt
                    if self.look_around_timer >= self.look_around_delay and not self.is_paused:
                        self.is_paused = True
                        self.pause_timer = random.uniform(0.4, 1.0)  # Longer pauses (more cautious)
                        self.look_around_timer = 0.0
                        self.look_around_delay = random.uniform(0.6, 2.5)
                    
                    if self.is_paused:
                        self.pause_timer -= dt
                        if self.pause_timer <= 0:
                            self.is_paused = False
                    else:
                        # Move slowly when approaching (thief is careful)
                        if self._follow_path(dt * 0.6, solid_rects, self.node_pos, proximity_threshold=TILE_SIZE * 0.5, door_rects=door_rects):
                            self.state = "looking_at_node"
                            self.look_around_timer = 0.0
                            self.look_around_delay = random.uniform(0.8, 2.0)  # Thief looks around longer
                            self.path = None
                            self.path_index = 0
                else:
                    self.approaching_node = False
                    self.is_paused = False
                    if self._follow_path(dt, solid_rects, self.node_pos, proximity_threshold=TILE_SIZE * 0.5, door_rects=door_rects):
                        self.state = "looking_at_node"
                        self.look_around_timer = 0.0
                        self.look_around_delay = random.uniform(0.8, 2.0)
                        self.path = None
                        self.path_index = 0
        elif self.state == "looking_at_node":
            # Thief looks around more carefully before "buying"
            self.look_around_timer += dt
            if self.look_around_timer >= self.look_around_delay:
                self.state = "buying"
                self.buying_time = random.uniform(1.5, 3.5)  # Thief is faster at buying
                self.buying_elapsed = 0.0
                self.look_around_timer = 0.0
        elif self.state == "buying":
            # Thief buys quickly (steals)
            self.buying_elapsed += dt
            if self.buying_elapsed >= self.buying_time:
                # Thief doesn't drop cash, just leaves
                self.state = "leaving"
                self.path = None
                self.path_index = 0
                self.approaching_node = False
                self.is_paused = False
                self._compute_path(self.leave_pos)
        elif self.state == "to_shelf":
            # Move towards a valid browsing position, not the shelf center
            if self.shelf_target is None:
                if self.browsing_positions:
                    self.shelf_target = random.choice(self.browsing_positions)
                else:
                    self.shelf_target = self.shelf_pos
                self._compute_path(self.shelf_target)
            
            # Check if we've reached the target browsing position
            if self._follow_path(dt, solid_rects, self.shelf_target, proximity_threshold=TILE_SIZE * 0.4, door_rects=door_rects):
                self.state = "browsing"
                self.browsing_elapsed = 0.0
                self.shelf_target = None
                self.path = None
                self.path_index = 0
                self._stuck_timer = 0.0
                self._pick_new_browsing_target()
        
        elif self.state == "browsing":
            self.browsing_elapsed += dt
            
            # After browsing for a while, switch to stealing mode
            if self.browsing_elapsed >= self.browsing_time:
                self.state = "searching"
                self.path = None
                self.path_index = 0
            else:
                # Walk around the shelf - pick new positions to walk to
                if self.browsing_target is None:
                    self._pick_new_browsing_target()
                else:
                    # Move towards browsing target using pathfinding
                    if self._follow_path(dt, solid_rects, self.browsing_target, proximity_threshold=TILE_SIZE * 0.4, door_rects=door_rects):
                        # Reached browsing target, pick a new one
                        self._pick_new_browsing_target()
        
        elif self.state == "searching":
            # Find all dodge coins on the floor
            if cash_items:
                # Pick a random dodge coin to steal
                self.target_cash = random.choice(cash_items)
                self.target_cash_pos = pygame.Vector2(self.target_cash.pos)
                self.state = "stealing"
                self._compute_path(self.target_cash_pos)
            else:
                # No dodge coins available, leave immediately
                self.state = "leaving"
                self._compute_path(self.leave_pos)
        
        elif self.state == "stealing":
            if self.target_cash_pos is None:
                self.state = "leaving"
                self._compute_path(self.leave_pos)
            elif self.target_cash and self.target_cash not in cash_items:
                # Dodge coin was already taken by someone else, leave
                self.target_cash = None
                self.target_cash_pos = None
                self.state = "leaving"
                self._compute_path(self.leave_pos)
            else:
                # Move towards the dodge coin
                if self._follow_path(dt, solid_rects, self.target_cash_pos, proximity_threshold=TILE_SIZE * 0.4, door_rects=door_rects):
                    # Reached dodge coin - steal it!
                    self.stole_cash = True
                    self.state = "leaving"
                    self.path = None
                    self.path_index = 0
                    self._compute_path(self.leave_pos)
        
        elif self.state == "leaving":
            # Use pathfinding to get to door first, then direct movement to exit
            # Check if we're at the door (within reasonable distance)
            distance_to_door = (self.position - self.door_pos).length()
            
            if distance_to_door < TILE_SIZE * 1.5:
                # At door, use direct movement to exit (outside map bounds)
                # Allow corner cutting when leaving
                if self._move_towards(self.leave_pos, dt, solid_rects, proximity_threshold=TILE_SIZE * 0.5, door_rects=door_rects, allow_corner_cutting=True):
                    self.finished = True
            else:
                # Not at door yet, use pathfinding to get there
                # Allow corner cutting when leaving
                if self.path is None or self.path_index >= len(self.path):
                    self._compute_path(self.door_pos)
                
                if self._follow_path(dt, solid_rects, self.door_pos, proximity_threshold=TILE_SIZE * 0.4, door_rects=door_rects, allow_corner_cutting=True):
                    # Reached door, path will be recomputed next frame to go to exit
                    self.path = None
                    self.path_index = 0

    def _compute_path(self, target: pygame.Vector2) -> None:
        """Compute A* path to target."""
        if self.tile_map:
            self.path = find_path(self.tile_map, self.position, target)
            self.path_index = 0
            self._stuck_timer = 0.0
            self._last_position = pygame.Vector2(self.position)
        else:
            self.path = None

    def _pick_new_browsing_target(self) -> None:
        """Pick a random valid floor tile position around the shelf to walk to while browsing.
        Only picks positions on the same side of the shelf as the customer's current position."""
        if self.browsing_positions:
            # Filter browsing positions to only those on the same side of the shelf
            # Calculate which side of the shelf the customer is currently on
            shelf_to_customer = self.position - self.shelf_pos
            if shelf_to_customer.length() < 1e-3:
                # Customer is at shelf center, use any position
                valid_positions = self.browsing_positions
            else:
                # Normalize direction from shelf to customer
                shelf_to_customer.normalize_ip()
                
                # Filter positions to only those on the same side (dot product > 0 means same general direction)
                valid_positions = []
                for pos in self.browsing_positions:
                    shelf_to_pos = pos - self.shelf_pos
                    if shelf_to_pos.length() < 1e-3:
                        continue  # Skip positions too close to shelf center
                    shelf_to_pos.normalize_ip()
                    # If dot product is positive, positions are on the same side
                    if shelf_to_customer.dot(shelf_to_pos) > 0.3:  # 0.3 threshold allows some variation
                        valid_positions.append(pos)
                
                # If no valid positions found on same side, use all positions as fallback
                if not valid_positions:
                    valid_positions = self.browsing_positions
            
            # Pick from filtered positions
            if valid_positions:
                self.browsing_target = random.choice(valid_positions)
                self._compute_path(self.browsing_target)
            else:
                # No valid positions, don't set target (will be handled by caller)
                self.browsing_target = None
        else:
            # Fallback: use old method if no browsing positions provided
            # Pick a random angle and distance around the shelf, but on the same side
            shelf_to_customer = self.position - self.shelf_pos
            if shelf_to_customer.length() > 1e-3:
                # Customer is not at shelf center, pick angle on same side
                current_angle = math.atan2(shelf_to_customer.y, shelf_to_customer.x)
                # Add some variation but stay on same side
                angle = current_angle + random.uniform(-math.pi / 3, math.pi / 3)
            else:
                angle = random.uniform(0, 2 * math.pi)  # Random angle if at center
            
            distance = random.uniform(TILE_SIZE * 1.5, TILE_SIZE * 2.5)  # Further out to avoid shelves
            
            # Calculate position around the shelf using trigonometry
            offset_x = distance * math.cos(angle)
            offset_y = distance * math.sin(angle)
            
            self.browsing_target = pygame.Vector2(
                self.shelf_pos.x + offset_x,
                self.shelf_pos.y + offset_y
            )
            self._compute_path(self.browsing_target)

    def _follow_path(self, dt: float, solid_rects: list[pygame.Rect], target: pygame.Vector2, proximity_threshold: float = TILE_SIZE * 0.3, door_rects: list[pygame.Rect] = None, allow_corner_cutting: bool = False) -> bool:
        """
        Follow the computed A* path. Returns True when target is reached.
        Falls back to direct movement if pathfinding fails.
        """
        # Check if we're already close enough to target
        distance_to_target = (self.position - target).length()
        if distance_to_target < proximity_threshold:
            self._stuck_timer = 0.0
            return True
        
        # Check if we're stuck (not moving)
        movement_distance = (self.position - self._last_position).length()
        if movement_distance < TILE_SIZE * 0.1:  # Hardly moved
            self._stuck_timer += dt
        else:
            self._stuck_timer = 0.0
            self._last_position = pygame.Vector2(self.position)
        
        # If stuck for more than 0.2 seconds, recompute path immediately
        # This prevents pushing through corners
        if self._stuck_timer > 0.2:
            # Always recompute path when stuck - don't skip waypoints as that can cause corner cutting
            self._compute_path(target)
            self._stuck_timer = 0.0
            self._last_position = pygame.Vector2(self.position)
        
        # Try to follow path if available
        if self.path and len(self.path) > 0 and self.path_index < len(self.path):
            # Follow the path
            next_waypoint = self.path[self.path_index]
            distance_to_waypoint = (self.position - next_waypoint).length()
            
            # Use a larger threshold for waypoints to avoid getting stuck on corners
            waypoint_threshold = max(proximity_threshold, TILE_SIZE * 0.5)
            
            if distance_to_waypoint < waypoint_threshold:
                # Reached waypoint, move to next
                self.path_index += 1
                if self.path_index >= len(self.path):
                    # Reached end of path, check if we're close to target
                    distance_to_target = (self.position - target).length()
                    return distance_to_target < proximity_threshold
                next_waypoint = self.path[self.path_index]
            
            # Move towards current waypoint
            self._move_towards(next_waypoint, dt, solid_rects, proximity_threshold=waypoint_threshold, door_rects=door_rects, allow_corner_cutting=allow_corner_cutting)
            return False  # Still following path
        else:
            # No path available or path exhausted, fall back to direct movement
            # Recompute path occasionally in case we got stuck
            if self.path is None or self.path_index >= len(self.path):
                # Only recompute if we haven't moved closer recently
                if self._last_path_recompute_pos is None or (self.position - self._last_path_recompute_pos).length() > TILE_SIZE * 2:
                    self._compute_path(target)
                    self._last_path_recompute_pos = pygame.Vector2(self.position)
            
            return self._move_towards(target, dt, solid_rects, proximity_threshold=proximity_threshold, door_rects=door_rects, allow_corner_cutting=allow_corner_cutting)

    def _move_towards(self, target: pygame.Vector2, dt: float, solid_rects: list[pygame.Rect], proximity_threshold: float = TILE_SIZE * 0.3, door_rects: list[pygame.Rect] = None, allow_corner_cutting: bool = False, use_player_speed: bool = False) -> bool:
        """
        Move towards target with collision detection. Returns True when within proximity_threshold.
        If allow_corner_cutting is True, allows slight phasing through obstacles to cut corners.
        """
        direction = target - self.position
        distance = direction.length()
        
        # Check if we're close enough to the target
        if distance < proximity_threshold:
            return True

        if distance < 1e-3:
            self.position.update(target)
            return True

        direction.normalize_ip()
        # Use player speed if in panic mode, otherwise use customer speed
        from config import PLAYER_SPEED
        speed = PLAYER_SPEED if use_player_speed else CUSTOMER_SPEED
        # Move per-frame like the player (multiply by FPS to convert from per-second to per-frame)
        step = speed * dt * FPS
        
        # Calculate movement vector
        move_x = direction.x * step
        move_y = direction.y * step
        
        # Helper function to check collision at a given position
        # Always allow corner cutting/phasing through obstacles
        def would_collide(pos: pygame.Vector2) -> bool:
            # Allow significant phasing through corners, shelves, and walls
            phase_amount = TILE_SIZE * 0.3  # Allow 30% phasing through obstacles
            effective_radius = max(self.radius - phase_amount, self.radius * 0.4)
            
            test_rect = pygame.Rect(
                int(pos.x - effective_radius),
                int(pos.y - effective_radius),
                effective_radius * 2,
                effective_radius * 2,
            )
            for tile_rect in solid_rects:
                if test_rect.colliderect(tile_rect):
                    return True
            return False
        
        # Strategy 1: Try full diagonal movement first
        new_pos = pygame.Vector2(self.position.x + move_x, self.position.y + move_y)
        if not would_collide(new_pos):
            self.position = new_pos
        else:
            # Strategy 2: Try moving on the axis with larger component first
            moved = False
            if abs(move_x) > abs(move_y):
                # Try X movement first
                new_pos_x = pygame.Vector2(self.position.x + move_x, self.position.y)
                if not would_collide(new_pos_x):
                    self.position = new_pos_x
                    moved = True
                else:
                    # Try Y movement only
                    new_pos_y = pygame.Vector2(self.position.x, self.position.y + move_y)
                    if not would_collide(new_pos_y):
                        self.position = new_pos_y
                        moved = True
            else:
                # Try Y movement first
                new_pos_y = pygame.Vector2(self.position.x, self.position.y + move_y)
                if not would_collide(new_pos_y):
                    self.position = new_pos_y
                    moved = True
                else:
                    # Try X movement only
                    new_pos_x = pygame.Vector2(self.position.x + move_x, self.position.y)
                    if not would_collide(new_pos_x):
                        self.position = new_pos_x
                        moved = True
            
            # Strategy 3: If we couldn't move directly, try sliding along walls
            # Use smaller perpendicular steps to slide around corners
            if not moved:
                # Try moving perpendicular to the direction (rotate 90 degrees)
                perp_x = -direction.y * step * 0.5  # Smaller step for sliding
                perp_y = direction.x * step * 0.5
                
                # Try both perpendicular directions
                perp_pos1 = pygame.Vector2(self.position.x + perp_x, self.position.y + perp_y)
                perp_pos2 = pygame.Vector2(self.position.x - perp_x, self.position.y - perp_y)
                
                if not would_collide(perp_pos1):
                    self.position = perp_pos1
                elif not would_collide(perp_pos2):
                    self.position = perp_pos2
                # If all fail, don't move (truly stuck)
        
        # Check if we're now close enough to the target after movement
        new_distance = (target - self.position).length()
        if new_distance < proximity_threshold:
            return True
        
        return False

    def draw(self, surface: pygame.Surface) -> None:
        # Draw outline behind customer body for visibility
        center = (int(self.position.x), int(self.position.y))
        outline_radius = self.radius + 5
        pygame.draw.circle(surface, (0, 0, 0), center, outline_radius)
        pygame.draw.circle(surface, self.color, center, self.radius)

