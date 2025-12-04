"""Main game state management."""

import threading
from typing import Union

import pygame

from config import COLOR_PLAYER, DAY_DURATION, PLAYER_RADIUS, TILE_SIZE
from entities import Cash, Customer, Litter, LitterCustomer, Player, ThiefCustomer
from map import TileMap, get_customer_solid_tiles_around, get_solid_tiles_around
from .ai_dialogue import AIDialogue
from .spawner import CustomerSpawner


class GameState:
    """Manages the main game state and game loop logic."""

    def __init__(self, tile_map: TileMap) -> None:
        self.tile_map = tile_map
        
        # Precompute important tile positions for customers
        door_centers = tile_map.find_tile_centers("D")  # TILE_DOOR
        # Treat connected shelves as one logical shelf by grouping them
        shelf_groups = self._compute_shelf_groups()  # List of (center, browsing_positions) tuples
        shelf_centers = [group[0] for group in shelf_groups]  # Extract just centers for spawner
        # Map center (as tuple) -> browsing positions for hashable keys
        self.shelf_browsing_positions = {(group[0].x, group[0].y): group[1] for group in shelf_groups}
        counter_centers = tile_map.find_tile_centers("C")  # TILE_COUNTER
        node_centers = tile_map.find_tile_centers("N")  # TILE_NODE - nodes customers can buy from

        door_pos = door_centers[0] if door_centers else pygame.Vector2(
            tile_map.cols * TILE_SIZE // 2, 
            tile_map.rows * TILE_SIZE // 2
        )

        # Initialize spawner
        self.spawner = CustomerSpawner(door_pos, shelf_centers, counter_centers, self.shelf_browsing_positions, tile_map, node_centers)

        # Game entities
        self.customers: list[Union[Customer, ThiefCustomer, LitterCustomer]] = []
        self.cash_items: list[Cash] = []  # Dodge coins dropped by customers
        self.litter_items: list[Litter] = []

        # Start roughly in the middle of the store on a floor tile
        start_col = 1
        start_row = 1
        start_x = start_col * TILE_SIZE + TILE_SIZE // 2
        start_y = start_row * TILE_SIZE + TILE_SIZE // 2

        self.player = Player(start_x, start_y, PLAYER_RADIUS, COLOR_PLAYER)

        # Day system
        self.current_day = 1
        self.day_timer = 0.0
        self.collected_coins = 0

        # Game state: "playing", "waiting_for_customers", "collection_time", "day_over_animation", "day_over", "tax_man"
        self.game_state = "playing"
        
        # Day over sequence timers
        self.collection_timer = 0.0
        self.day_over_animation_progress = 0.0
        self.day_over_animation_duration = 1.0  # 1 second animation
        self.sound_played = False  # Track if day over sound has been played
        self.video_playing = False  # Track if video is currently playing
        
        # Sound will be set from main.py
        self.day_over_sound = None
        
        # Tax man menu state
        self.tax_man_menu_selection = 0  # 0 = Pay, 1 = Argue
        self.tax_man_ai_response: str | None = None  # Store AI response when arguing
        self.tax_man_awaiting_response = False  # Track if waiting for AI response
        self.tax_man_tax_amount = 0  # Calculate tax amount
        self.tax_man_input_mode = True  # Always in input mode for chat
        self.tax_man_player_argument = ""  # Store player's typed message
        self.tax_man_conversation: list[dict[str, str]] = []  # Conversation history: [{"sender": "player"/"boss", "message": "..."}, ...]
        self._pending_ai_request = None  # Track pending AI request thread
        
        # Initialize AI dialogue system
        self.ai_dialogue = AIDialogue()

    def update(self, dt: float) -> None:
        """Update game state."""
        # Update day timer
        if self.game_state == "playing":
            self.day_timer += dt
            if self.day_timer >= DAY_DURATION:
                self.game_state = "waiting_for_customers"
                # Force all customers to start leaving
                for customer in self.customers:
                    if customer.state != "leaving":
                        customer.state = "leaving"
                        customer.path = None
                        customer.path_index = 0
        
        # Only update game logic if we're in a state that allows gameplay
        if self.game_state not in ("playing", "waiting_for_customers", "collection_time"):
            # Video playback is handled in renderer, no need to update animation progress here
            return

        # Handle player input and movement
        direction = self.player.handle_input()
        solid_rects = get_solid_tiles_around(self.player.rect, self.tile_map)
        self.player.move_and_collide(direction, solid_rects)

        # Check for dodge coin collection (when player walks over it)
        player_rect = self.player.rect
        coins_to_remove = []
        for coin in self.cash_items:
            # Create a small rect around the dodge coin position for collision
            coin_size = TILE_SIZE // 4
            coin_rect = pygame.Rect(
                int(coin.pos.x - coin_size / 2),
                int(coin.pos.y - coin_size / 2),
                coin_size,
                coin_size,
            )
            if player_rect.colliderect(coin_rect):
                coins_to_remove.append(coin)
                self.collected_coins += 1

        # Remove collected dodge coins
        for coin in coins_to_remove:
            if coin in self.cash_items:
                self.cash_items.remove(coin)

        # Spawn customers (only during playing state)
        if self.game_state == "playing":
            new_customer = self.spawner.update(dt, self.customers)
            if new_customer:
                self.customers.append(new_customer)

        # Update customers
        for customer in self.customers:
            customer_obstacle_rects, customer_door_rects = get_customer_solid_tiles_around(customer.rect, self.tile_map)
            # Customers only collide with obstacles, NOT doors (they phase through doors)
            # Door rects are passed separately but not used for collision
            
            # Handle different customer types
            if isinstance(customer, ThiefCustomer):
                # Thief customer needs access to dodge coins to find targets
                customer.update(dt, customer_obstacle_rects, self.cash_items, customer_door_rects)
                if customer.stole_cash and customer.target_cash:
                    # Remove the stolen dodge coin
                    if customer.target_cash in self.cash_items:
                        self.cash_items.remove(customer.target_cash)
                    customer.stole_cash = False
                    customer.target_cash = None
            elif isinstance(customer, LitterCustomer):
                # Litter customer drops litter
                customer.update(dt, customer_obstacle_rects, customer_door_rects)
                if customer.drop_litter and customer.litter_pos:
                    # Place litter where customer dropped it
                    self.litter_items.append(Litter(customer.litter_pos))
                    customer.drop_litter = False
                    customer.litter_pos = None
            else:
                # Regular customer drops dodge coins
                customer.update(dt, customer_obstacle_rects, customer_door_rects)
                if customer.drop_cash:
                    # Place dodge coin at the shelf position where customer is standing
                    self.cash_items.append(Cash(customer.position))
                    customer.drop_cash = False

        # Remove customers that have left
        self.customers = [c for c in self.customers if not c.finished]
        
        # Handle state transitions for day over sequence
        if self.game_state == "waiting_for_customers":
            # Check if all customers have left
            if len(self.customers) == 0:
                self.game_state = "collection_time"
                self.collection_timer = 0.0
        elif self.game_state == "collection_time":
            # Wait 5 seconds for coin collection
            self.collection_timer += dt
            if self.collection_timer >= 5.0:
                # Transition to animation state and play sound
                self.game_state = "day_over_animation"
                self.day_over_animation_progress = 0.0
                self.video_playing = True  # Signal that video should start playing
                # Play sound when entering animation state
                if not self.sound_played and self.day_over_sound is not None:
                    try:
                        self.day_over_sound.play()
                        self.sound_played = True
                    except Exception as e:
                        print(f"Warning: Could not play day over sound: {e}")

    def handle_event(self, event: pygame.event.Event, renderer=None) -> bool:
        """
        Handle pygame events. Returns True if event was handled and should stop propagation.
        
        Args:
            event: The pygame event to handle
            renderer: Optional Renderer instance for checking Venmo bubble clicks
        """
        if event.type == pygame.QUIT:
            return True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Check if clicking on Venmo bubble in tax_man state
            if self.game_state == "tax_man" and renderer is not None:
                mouse_pos = event.pos
                if renderer.is_venmo_bubble_clicked(mouse_pos):
                    # Clicked on Venmo bubble - pay tax and continue
                    self.collected_coins = max(0, self.collected_coins - self.tax_man_tax_amount)
                    self._start_new_day()
                    return False  # Event handled but don't stop propagation
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return True
            # Handle "I" key to end the day early
            if event.key == pygame.K_i:
                if self.game_state == "playing":
                    # End the day - force customers to leave
                    self.game_state = "waiting_for_customers"
                    for customer in self.customers:
                        if customer.state != "leaving":
                            customer.state = "leaving"
                            customer.path = None
                            customer.path_index = 0
                elif self.game_state == "waiting_for_customers":
                    # Skip to collection time
                    if len(self.customers) == 0:
                        self.game_state = "collection_time"
                        self.collection_timer = 0.0
                elif self.game_state == "collection_time":
                    # Skip directly to day over animation
                    self.game_state = "day_over_animation"
                    self.day_over_animation_progress = 0.0
                    self.video_playing = True
                    # Play sound when entering animation state
                    if not self.sound_played and self.day_over_sound is not None:
                        try:
                            self.day_over_sound.play()
                            self.sound_played = True
                        except Exception as e:
                            print(f"Warning: Could not play day over sound: {e}")
            # Handle day over and tax man screen transitions
            if self.game_state == "day_over_animation":
                # Any key press transitions to tax man screen
                self.game_state = "tax_man"
                # Calculate tax amount (10% of collected coins, minimum 1)
                self.tax_man_tax_amount = max(1, int(self.collected_coins * 0.1))
                self.tax_man_menu_selection = 0
                self.tax_man_ai_response = None
                self.tax_man_awaiting_response = False
                self.tax_man_input_mode = True  # Enable input mode for chat
                self.tax_man_player_argument = ""
                self.tax_man_conversation = []  # Initialize conversation history
            elif self.game_state == "day_over":
                # Legacy state - transition to tax man
                self.game_state = "tax_man"
                self.tax_man_tax_amount = max(1, int(self.collected_coins * 0.1))
                self.tax_man_menu_selection = 0
                self.tax_man_ai_response = None
                self.tax_man_awaiting_response = False
                self.tax_man_input_mode = True  # Enable input mode for chat
                self.tax_man_player_argument = ""
                self.tax_man_conversation = []  # Initialize conversation history
            elif self.game_state == "tax_man":
                # Handle chat input in tax man screen
                if self.tax_man_input_mode:
                    if event.key == pygame.K_RETURN:
                        # Send message instantly
                        if self.tax_man_player_argument.strip():
                            # Store message and clear input immediately
                            player_msg = self.tax_man_player_argument.strip()
                            self.tax_man_player_argument = ""  # Clear input instantly so it's visible immediately
                            
                            # Add player message to conversation immediately
                            self.tax_man_conversation.append({
                                "sender": "player",
                                "message": player_msg
                            })
                            
                            # Set awaiting response flag
                            self.tax_man_awaiting_response = True
                            
                            # Make API call in a separate thread so it doesn't block the screen update
                            def get_ai_response():
                                boss_response = self.ai_dialogue.generate_tax_argument(
                                    self.collected_coins, 
                                    self.current_day, 
                                    player_msg
                                )
                                # Add boss response to conversation (thread-safe, only called from one thread)
                                self.tax_man_conversation.append({
                                    "sender": "boss",
                                    "message": boss_response
                                })
                                self.tax_man_awaiting_response = False
                                self.tax_man_ai_response = boss_response
                            
                            # Start the API call in a background thread
                            self._pending_ai_request = threading.Thread(target=get_ai_response, daemon=True)
                            self._pending_ai_request.start()
                    elif event.key == pygame.K_BACKSPACE:
                        # Delete last character
                        self.tax_man_player_argument = self.tax_man_player_argument[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        # Add character (limit to 200 characters)
                        if len(self.tax_man_player_argument) < 200:
                            self.tax_man_player_argument += event.unicode
        return False

    def _start_new_day(self) -> None:
        """Reset game state for a new day."""
        self.current_day += 1
        self.day_timer = 0.0
        # Clear all uncollected dodge coins
        self.cash_items.clear()
        # Clear all customers
        self.customers.clear()
        # Clear all litter
        self.litter_items.clear()
        # Reset game state to playing
        self.game_state = "playing"
        # Reset day over sequence timers
        self.collection_timer = 0.0
        self.day_over_animation_progress = 0.0
        self.sound_played = False
        self.video_playing = False  # Reset video playing state
        # Reset tax man menu state
        self.tax_man_menu_selection = 0
        self.tax_man_ai_response = None
        self.tax_man_awaiting_response = False
        self.tax_man_tax_amount = 0
        self.tax_man_input_mode = True
        self.tax_man_player_argument = ""
        self.tax_man_conversation = []

    def _compute_shelf_groups(self) -> list[tuple[pygame.Vector2, list[pygame.Vector2]]]:
        """
        Group connected shelf tiles (4-directional) and return (center, browsing_positions) per group.
        This makes each connected block of 'S' tiles behave as a single shelf target.
        browsing_positions are valid floor tiles around the shelf that customers can walk on.
        """
        shelves: list[tuple[pygame.Vector2, list[pygame.Vector2]]] = []
        visited: set[tuple[int, int]] = set()

        rows = self.tile_map.rows
        cols = self.tile_map.cols

        for row in range(rows):
            for col in range(cols):
                if (row, col) in visited:
                    continue
                if self.tile_map.tile_at(col, row) != "S":
                    continue

                # Flood fill to collect all connected 'S' tiles
                stack: list[tuple[int, int]] = [(row, col)]
                group: list[tuple[int, int]] = []

                while stack:
                    r, c = stack.pop()
                    if (r, c) in visited:
                        continue
                    if self.tile_map.tile_at(c, r) != "S":
                        continue
                    visited.add((r, c))
                    group.append((r, c))

                    # 4-directional neighbors
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                            if self.tile_map.tile_at(nc, nr) == "S":
                                stack.append((nr, nc))

                if not group:
                    continue

                # Compute world-space center of the whole group
                sum_x = 0
                sum_y = 0
                for r, c in group:
                    x = c * TILE_SIZE + TILE_SIZE // 2
                    y = r * TILE_SIZE + TILE_SIZE // 2
                    sum_x += x
                    sum_y += y

                count = len(group)
                center = pygame.Vector2(sum_x / count, sum_y / count)
                
                # Find valid floor tiles around this shelf group for browsing
                browsing_positions = self.tile_map.find_floor_tiles_around_shelf_group(center, search_radius=3)
                
                # If no browsing positions found, use positions further out
                if not browsing_positions:
                    browsing_positions = self.tile_map.find_floor_tiles_around_shelf_group(center, search_radius=5)
                
                shelves.append((center, browsing_positions))

        return shelves

