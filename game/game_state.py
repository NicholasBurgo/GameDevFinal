"""Main game state management."""

import threading
from typing import Union

import pygame

from config import COLOR_PLAYER, DAY_DURATION, PLAYER_RADIUS, TILE_OFFICE_DOOR, TILE_SIZE
from entities import Cash, Customer, Litter, LitterCustomer, Player, ThiefCustomer
from map import TileMap, get_customer_solid_tiles_around, get_solid_tiles_around
from map.tile_map import OFFICE_MAP, STORE_MAP
from .ai_dialogue import AIDialogue
from .spawner import CustomerSpawner


class GameState:
    """Manages the main game state and game loop logic."""

    def __init__(self, tile_map: TileMap) -> None:
        # Create both room maps
        self.store_map = TileMap(STORE_MAP)
        self.office_map = TileMap(OFFICE_MAP)
        self.tile_map = tile_map  # Current active map (starts as store)
        
        # Room system
        self.current_room = "store"  # "store" or "office"
        # Store player positions in each room for seamless transitions
        self.player_positions = {
            "store": None,  # Will be set on first spawn
            "office": None
        }
        # Track if player was on door last frame to prevent rapid transitions
        self._was_on_door = False
        # Camera offset for room transitions (office is above store)
        self.camera_y_offset = 0.0  # Offset to shift view to active room
        
        # Precompute important tile positions for customers (use store map)
        door_centers = self.store_map.find_tile_centers("D")  # TILE_DOOR
        # Treat connected shelves as one logical shelf by grouping them (use store map)
        shelf_groups = self._compute_shelf_groups()  # List of (center, browsing_positions) tuples
        shelf_centers = [group[0] for group in shelf_groups]  # Extract just centers for spawner
        # Map center (as tuple) -> browsing positions for hashable keys
        self.shelf_browsing_positions = {(group[0].x, group[0].y): group[1] for group in shelf_groups}
        counter_centers = self.store_map.find_tile_centers("C")  # TILE_COUNTER
        node_centers = self.store_map.find_tile_centers("N")  # TILE_NODE - nodes customers can buy from

        door_pos = door_centers[0] if door_centers else pygame.Vector2(
            self.store_map.cols * TILE_SIZE // 2, 
            self.store_map.rows * TILE_SIZE // 2
        )

        # Initialize spawner (customers only in store)
        self.spawner = CustomerSpawner(door_pos, shelf_centers, counter_centers, self.shelf_browsing_positions, self.store_map, node_centers)

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
        self.player_positions["store"] = pygame.Vector2(start_x, start_y)
        
        # Find office door position in store (for transitioning to office)
        office_door_centers = self.store_map.find_tile_centers(TILE_OFFICE_DOOR)
        self.store_office_door_pos = office_door_centers[0] if office_door_centers else None
        
        # Calculate office position (office is stacked above store)
        # Office world Y position starts after store ends
        self.store_world_height = self.store_map.rows * TILE_SIZE
        self.office_world_y_offset = self.store_world_height  # Office starts below store in world space
        
        # Find office door position in office (for transitioning back to store)
        # Office door in office map will be at a specific location
        office_start_col = 4  # Column 4 (where door is in office map)
        office_start_row = 3  # Row 3 (where door is in office map)
        office_start_x = office_start_col * TILE_SIZE + TILE_SIZE // 2
        # Add world offset so office is below store
        office_start_y = self.office_world_y_offset + (office_start_row * TILE_SIZE + TILE_SIZE // 2)
        self.player_positions["office"] = pygame.Vector2(office_start_x, office_start_y)
        
        # Initial camera is at store (no offset)
        self.camera_y_offset = 0.0

        # Day system
        self.current_day = 1
        self.day_timer = 0.0
        self.collected_coins = 0

        # Game state: "playing", "waiting_for_customers", "collection_time", "day_over_animation", "day_over", "tax_man_notification", "tax_man", "boss_fight"
        self.game_state = "playing"
        
        # Day over sequence timers
        self.collection_timer = 0.0
        self.day_over_animation_progress = 0.0
        self.day_over_animation_duration = 1.0  # 1 second animation
        self.sound_played = False  # Track if day over sound has been played
        self.video_playing = False  # Track if video is currently playing
        
        # Tax man notification - appears around 1 PM
        # 10 AM to 5 PM is 7 hours, 1 PM is 3 hours in = 3/7 of day duration
        self.tax_man_notification_shown = False  # Track if notification has been shown this day
        
        # Sound will be set from main.py
        self.day_over_sound = None
        
        # Tax man menu state
        self.tax_man_menu_selection = 0  # 0 = Pay, 1 = Argue
        self.tax_man_ai_response: str | None = None  # Store AI response when arguing
        self.tax_man_awaiting_response = False  # Track if waiting for AI response
        self.tax_man_tax_amount = 0  # Calculate tax amount
        self.tax_man_original_tax_amount = 0  # Original tax amount before arguments
        self.tax_man_input_mode = True  # Always in input mode for chat
        self.tax_man_player_argument = ""  # Store player's typed message
        self.tax_man_conversation: list[dict[str, str]] = []  # Conversation history: [{"sender": "player"/"boss", "message": "..."}, ...]
        self._pending_ai_request = None  # Track pending AI request thread
        
        # Anger and persuasion system
        self.tax_man_anger = 0.0  # Anger level (0-100%)
        self.tax_man_argument_count = 0  # How many times player has argued (persists across days)
        self.tax_man_persuasion_bonus = 0.0  # Bonus to persuasion chance (increases by 5% each argument, capped at 20%)
        self.tax_man_notification_timer = 0.0  # Timer for notification (if ignored, triggers boss fight)
        self.tax_man_notification_timeout = 10.0  # 10 seconds to respond to notification
        self.tax_man_boss_fight_next_day = False  # Flag to trigger boss fight on next day
        self.tax_man_boss_fight_triggered = False  # Flag to track if boss fight was triggered (keep phone open)
        self.tax_man_has_paid = False  # Track if player has paid the tax
        
        # Initialize AI dialogue system
        self.ai_dialogue = AIDialogue()

    def update(self, dt: float) -> None:
        """Update game state."""
        # Update day timer - runs during playing and notification, pauses during tax man menu
        if self.game_state in ("playing", "tax_man_notification"):
            self.day_timer += dt
            # Check for tax man notification trigger (around 1 PM)
            # Only trigger on day 2 and onwards (not on day 1)
            # 10 AM to 5 PM is 7 hours, 1 PM is 3 hours in = 3/7 ≈ 0.4286 of day duration
            if self.game_state == "playing":
                tax_man_trigger_time = DAY_DURATION * (3.0 / 7.0)
                if (self.day_timer >= tax_man_trigger_time 
                    and not self.tax_man_notification_shown 
                    and self.current_day >= 2):
                    self.game_state = "tax_man_notification"
                    self.tax_man_tax_amount = max(1, int(self.collected_coins * 0.1))
                    self.tax_man_original_tax_amount = self.tax_man_tax_amount
                    self.tax_man_notification_shown = True
                    self.tax_man_notification_timer = 0.0  # Reset notification timer
                elif self.day_timer >= DAY_DURATION:
                    self.game_state = "waiting_for_customers"
                    # Force all customers to start leaving
                    for customer in self.customers:
                        if customer.state != "leaving":
                            customer.state = "leaving"
                            customer.path = None
                            customer.path_index = 0
            elif self.game_state == "tax_man_notification":
                # Timer for notification timeout (if ignored, trigger boss fight next day)
                self.tax_man_notification_timer += dt
                if self.tax_man_notification_timer >= self.tax_man_notification_timeout:
                    # Notification ignored - trigger boss fight next day
                    self.tax_man_boss_fight_next_day = True
                    self.tax_man_notification_timer = 0.0
                # Timer continues during notification, check for day end
                if self.day_timer >= DAY_DURATION:
                    self.game_state = "waiting_for_customers"
                    # Force all customers to start leaving
                    for customer in self.customers:
                        if customer.state != "leaving":
                            customer.state = "leaving"
                            customer.path = None
                            customer.path_index = 0
        
        # Check persuasion after AI response is received (in main thread)
        if self.game_state == "tax_man" and not self.tax_man_awaiting_response:
            # Check if we just received a response (conversation has boss message at the end)
            if self.tax_man_conversation and self.tax_man_conversation[-1].get("sender") == "boss":
                # Track which message we last checked persuasion for
                if not hasattr(self, '_last_persuasion_check_index'):
                    self._last_persuasion_check_index = -1
                
                # Check persuasion if we haven't checked for this message yet
                current_message_count = len(self.tax_man_conversation)
                if current_message_count > self._last_persuasion_check_index:
                    self._last_persuasion_check_index = current_message_count
                    self._check_persuasion()
        
        # Only update game logic if we're in a state that allows gameplay
        if self.game_state not in ("playing", "waiting_for_customers", "collection_time", "tax_man_notification"):
            # Video playback is handled in renderer, no need to update animation progress here
            return

        # Handle player input and movement
        direction = self.player.handle_input()
        # Adjust player rect for collision detection (account for world offset)
        player_rect_for_collision = self.player.rect.copy()
        if self.current_room == "office":
            # Adjust Y coordinate to local room coordinates for collision check
            player_rect_for_collision.y -= self.office_world_y_offset
        # Get solid tiles with coordinate adjustment
        solid_rects = self._get_solid_tiles_with_offset(player_rect_for_collision, self.tile_map)
        self.player.move_and_collide(direction, solid_rects)
        
        # Save player position in current room
        self.player_positions[self.current_room] = pygame.Vector2(self.player.x, self.player.y)
        
        # Check for office door collision to transition rooms
        self._check_room_transition()

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

        # Only update store entities when in store room
        if self.current_room == "store":
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
                    # Check if player can pay
                    if self.collected_coins >= self.tax_man_tax_amount:
                        # Clicked on Venmo bubble - pay tax
                        self.collected_coins = max(0, self.collected_coins - self.tax_man_tax_amount)
                        self.tax_man_has_paid = True
                        # Don't close automatically - user can close with SPACE
                        return False  # Event handled but don't stop propagation
                    else:
                        # Can't pay - trigger boss fight next day
                        self.tax_man_boss_fight_next_day = True
                        self.tax_man_boss_fight_triggered = True
                        return False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return True
            # Handle "O" key to activate boss fight anytime
            if event.key == pygame.K_o:
                if self.game_state == "playing":
                    self.game_state = "boss_fight"
                    return False
                elif self.game_state == "boss_fight":
                    # Exit boss fight and return to playing
                    self.game_state = "playing"
                    return False
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
            # Handle day over screen transitions
            # Note: Tax man menu is ONLY accessible from notification, not from day over
            if self.game_state == "day_over_animation":
                # Any key press starts a new day (tax man is only accessible via notification)
                self._start_new_day()
            elif self.game_state == "day_over":
                # Legacy state - start a new day (tax man is only accessible via notification)
                self._start_new_day()
            elif self.game_state == "tax_man_notification":
                # Space key opens tax man menu from notification
                if event.key == pygame.K_SPACE:
                    self.game_state = "tax_man"
                    self.tax_man_menu_selection = 0
                    self.tax_man_ai_response = None
                    self.tax_man_awaiting_response = False
                    self.tax_man_input_mode = True
                    self.tax_man_player_argument = ""
                    self.tax_man_conversation = []
                    # Reset notification timer when opening menu
                    self.tax_man_notification_timer = 0.0
            elif self.game_state == "tax_man":
                # Space key closes tax man screen (can close anytime)
                if event.key == pygame.K_SPACE:
                    # Check if player has paid - if not, trigger boss fight next day
                    if not self.tax_man_has_paid and not self.tax_man_boss_fight_triggered:
                        # Player closed without paying - trigger boss fight next day
                        self.tax_man_boss_fight_next_day = True
                        self.tax_man_boss_fight_triggered = True
                    # Close phone and return to gameplay
                    self.game_state = "playing"
                    self._reset_tax_man_state()
                    return False
                # Handle chat input in tax man screen (only if boss fight not triggered)
                if not self.tax_man_boss_fight_triggered and self.tax_man_input_mode:
                    if event.key == pygame.K_RETURN:
                        # Send message instantly
                        if self.tax_man_player_argument.strip():
                            # Store message and clear input immediately
                            player_msg = self.tax_man_player_argument.strip()
                            self.tax_man_player_argument = ""  # Clear input instantly so it's visible immediately
                            
                            # Check if this is the start of a new argument session (first message in conversation)
                            is_new_argument_session = len(self.tax_man_conversation) == 0
                            
                            # If this is the second time arguing (argument_count == 1), trigger boss fight next day
                            if is_new_argument_session and self.tax_man_argument_count == 1:
                                self.tax_man_boss_fight_next_day = True
                                self.tax_man_boss_fight_triggered = True
                                # Add a message to conversation indicating boss fight will happen
                                self.tax_man_conversation.append({
                                    "sender": "boss",
                                    "message": "You've pushed me too far. See you tomorrow."
                                })
                                return False
                            
                            # Initialize anger at 20% on first message of argument session
                            if self.tax_man_anger == 0.0:
                                self.tax_man_anger = 20.0
                            
                            # Increase anger by 5-15% per message
                            import random
                            anger_increase = random.uniform(5.0, 15.0)
                            self.tax_man_anger = min(100.0, self.tax_man_anger + anger_increase)
                            
                            # Increment argument count (only on first message of argument session)
                            if is_new_argument_session:
                                self.tax_man_argument_count += 1
                                
                                # If first time arguing, increase tax amount by 1
                                if self.tax_man_argument_count == 1:
                                    self.tax_man_tax_amount = self.tax_man_original_tax_amount + 1
                            
                            # Add player message to conversation immediately
                            self.tax_man_conversation.append({
                                "sender": "player",
                                "message": player_msg
                            })
                            
                            # Check if anger reached 100% - trigger boss fight next day
                            if self.tax_man_anger >= 100.0:
                                self.tax_man_boss_fight_next_day = True
                                self.tax_man_boss_fight_triggered = True
                                # Add a message to conversation indicating boss fight will happen
                                self.tax_man_conversation.append({
                                    "sender": "boss",
                                    "message": "You've pushed me too far. See you tomorrow."
                                })
                                return False
                            
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
                                # Persuasion will be checked in main thread after response is added
                            
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
        
        # Check if boss fight should happen this day
        if self.tax_man_boss_fight_next_day:
            self.game_state = "boss_fight"
            self.tax_man_boss_fight_next_day = False  # Reset flag
        else:
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
        self.tax_man_notification_shown = False  # Reset notification flag
        # Don't reset argument count or persuasion bonus - they persist across days
        # Reset anger and conversation for new day
        self.tax_man_anger = 0.0
        self.tax_man_conversation = []
        self.tax_man_original_tax_amount = 0
        self.tax_man_notification_timer = 0.0
        self.tax_man_boss_fight_triggered = False  # Reset boss fight triggered flag (but keep boss_fight_next_day if set)
        self.tax_man_has_paid = False  # Reset payment flag
        if hasattr(self, '_last_persuasion_check_index'):
            self._last_persuasion_check_index = -1

    def _check_persuasion(self) -> None:
        """Check if player successfully persuades the tax man."""
        import random
        
        # Calculate persuasion chance
        if self.tax_man_argument_count == 1:
            # First time: 70% chance
            persuasion_chance = 70.0
        else:
            # Subsequent times: 0-50% based on anger level
            # Higher anger = lower chance (inverse relationship)
            # At 0% anger: 50% chance, at 100% anger: 0% chance
            persuasion_chance = max(0.0, 50.0 - (self.tax_man_anger * 0.5))
        
        # Add persuasion bonus (increases by 5% each argument, capped at 20%)
        persuasion_chance = min(100.0, persuasion_chance + self.tax_man_persuasion_bonus)
        
        # Roll for persuasion
        roll = random.uniform(0.0, 100.0)
        if roll <= persuasion_chance:
            # Successfully persuaded - let them go without paying
            self.tax_man_has_paid = True  # Count persuasion as "paid" (no payment needed)
            # Add a message to conversation indicating success
            self.tax_man_conversation.append({
                "sender": "boss",
                "message": "Fine, you win this time. But don't push your luck."
            })
            # Don't close automatically - user can close with SPACE
            # Increase persuasion bonus for next time (capped at 20%)
            self.tax_man_persuasion_bonus = min(20.0, self.tax_man_persuasion_bonus + 5.0)
        # If not persuaded, continue the conversation (player can keep arguing)

    def _reset_tax_man_state(self) -> None:
        """Reset tax man state after paying or being persuaded."""
        self.tax_man_anger = 0.0
        self.tax_man_conversation = []
        self.tax_man_ai_response = None
        self.tax_man_awaiting_response = False
        self.tax_man_input_mode = True
        self.tax_man_player_argument = ""
        self.tax_man_tax_amount = 0
        self.tax_man_original_tax_amount = 0
        self.tax_man_notification_timer = 0.0
        if hasattr(self, '_last_persuasion_check_index'):
            self._last_persuasion_check_index = -1

    def _check_room_transition(self) -> None:
        """Check if player is on an office door and transition rooms if needed."""
        player_col = int(self.player.x // TILE_SIZE)
        # Convert world Y to local room Y coordinate
        if self.current_room == "office":
            # Player Y is in world coordinates, subtract office offset to get local
            player_local_y = self.player.y - self.office_world_y_offset
            player_row = int(player_local_y // TILE_SIZE)
        else:
            # Store room starts at Y=0, so player Y is already local
            player_row = int(self.player.y // TILE_SIZE)
        
        current_tile = self.tile_map.tile_at(player_col, player_row)
        is_on_door = current_tile == TILE_OFFICE_DOOR
        
        # Only transition when player first steps onto door (not every frame they're on it)
        if is_on_door and not self._was_on_door:
            # Transition to the other room
            if self.current_room == "store":
                # Transition to office
                self.current_room = "office"
                self.tile_map = self.office_map
                # Move camera to office (office is below store, so positive offset)
                self.camera_y_offset = self.office_world_y_offset
                # Restore player position in office (or set initial position)
                if self.player_positions["office"] is not None:
                    self.player.x = self.player_positions["office"].x
                    self.player.y = self.player_positions["office"].y
                else:
                    # First time entering office - place near door position
                    office_start_col = 4
                    office_start_row = 3
                    self.player.x = office_start_col * TILE_SIZE + TILE_SIZE // 2
                    self.player.y = self.office_world_y_offset + (office_start_row * TILE_SIZE + TILE_SIZE // 2)
                    self.player_positions["office"] = pygame.Vector2(self.player.x, self.player.y)
            else:
                # Transition back to store
                self.current_room = "store"
                self.tile_map = self.store_map
                # Move camera back to store (no offset)
                self.camera_y_offset = 0.0
                # Restore player position in store
                if self.player_positions["store"] is not None:
                    self.player.x = self.player_positions["store"].x
                    self.player.y = self.player_positions["store"].y
                else:
                    # Fallback to door position
                    if self.store_office_door_pos:
                        self.player.x = self.store_office_door_pos.x
                        self.player.y = self.store_office_door_pos.y
                        self.player_positions["store"] = pygame.Vector2(self.player.x, self.player.y)
        
        # Update door tracking for next frame
        self._was_on_door = is_on_door
    
    def _get_solid_tiles_with_offset(self, rect: pygame.Rect, tile_map) -> list[pygame.Rect]:
        """Get solid tiles for collision, adjusting for room coordinate system.
        
        Args:
            rect: Player rect in LOCAL room coordinates (already adjusted)
            tile_map: The current tile map (store or office)
            
        Returns:
            List of solid tile rects in WORLD coordinates
        """
        from config import SOLID_TILES, TILE_SIZE
        
        tiles: list[pygame.Rect] = []
        y_offset = self.office_world_y_offset if self.current_room == "office" else 0

        # rect is already in local coordinates, so we can use it directly
        left = max(rect.left // TILE_SIZE - 1, 0)
        right = min(rect.right // TILE_SIZE + 1, tile_map.cols - 1)
        top = max(rect.top // TILE_SIZE - 1, 0)
        bottom = min(rect.bottom // TILE_SIZE + 1, tile_map.rows - 1)

        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if tile_map.tile_at(col, row) in SOLID_TILES:
                    x = col * TILE_SIZE
                    y = row * TILE_SIZE + y_offset  # Convert to world coordinates
                    tiles.append(pygame.Rect(x, y, TILE_SIZE, TILE_SIZE))

        return tiles

    def _compute_shelf_groups(self) -> list[tuple[pygame.Vector2, list[pygame.Vector2]]]:
        """
        Group connected shelf tiles (4-directional) and return (center, browsing_positions) per group.
        This makes each connected block of 'S' tiles behave as a single shelf target.
        browsing_positions are valid floor tiles around the shelf that customers can walk on.
        """
        shelves: list[tuple[pygame.Vector2, list[pygame.Vector2]]] = []
        visited: set[tuple[int, int]] = set()

        rows = self.store_map.rows
        cols = self.store_map.cols

        for row in range(rows):
            for col in range(cols):
                if (row, col) in visited:
                    continue
                if self.store_map.tile_at(col, row) != "S":
                    continue

                # Flood fill to collect all connected 'S' tiles
                stack: list[tuple[int, int]] = [(row, col)]
                group: list[tuple[int, int]] = []

                while stack:
                    r, c = stack.pop()
                    if (r, c) in visited:
                        continue
                    if self.store_map.tile_at(c, r) != "S":
                        continue
                    visited.add((r, c))
                    group.append((r, c))

                    # 4-directional neighbors
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                            if self.store_map.tile_at(nc, nr) == "S":
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
                browsing_positions = self.store_map.find_floor_tiles_around_shelf_group(center, search_radius=3)
                
                # If no browsing positions found, use positions further out
                if not browsing_positions:
                    browsing_positions = self.tile_map.find_floor_tiles_around_shelf_group(center, search_radius=5)
                
                shelves.append((center, browsing_positions))

        return shelves

