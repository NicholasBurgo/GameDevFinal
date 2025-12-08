"""Main game state management."""

import math
import random
import threading
from typing import Union

import pygame

from config import COLOR_PLAYER, CUSTOMER_SPEED, DAY_DURATION, FPS, PLAYER_RADIUS, TILE_ACTIVATION, TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3, TILE_COMPUTER, TILE_OFFICE_DOOR, TILE_SIZE
from entities import Cash, Customer, Litter, LitterCustomer, Player, ThiefCustomer
from map import TileMap, find_path, get_customer_solid_tiles_around, get_solid_tiles_around
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

        # Slot machine state
        self.slot_bet: int = 0
        self.slot_message: str = "Enter bet and press Enter."
        self.slot_reels: list[str] = ["♠", "♥", "♦"]
        self.slot_spinning: bool = False
        self.slot_spin_timer: float = 0.0
        self.slot_spin_tick_timer: float = 0.0
        self.slot_spin_duration: float = 1.5
        self.slot_spin_tick: float = 0.08
        self.slot_current_bet: int = 0
        self.slot_spin_result: dict | None = None

        # Mystery box (Computer 2)
        self.mystery_items = [
            {"key": "nuke", "name": "Nuke", "damage": 99999, "chance": 0.10, "desc": "Screen whites out. Game over."},
            {"key": "water_gun", "name": "Water Gun", "damage": 10, "chance": 0.30, "desc": "A weak boss fight."},
            {"key": "paper_plane", "name": "Paper Plane", "damage": 25, "chance": 0.20, "desc": "Another weak boss fight."},
            {"key": "nothing", "name": "Nothing", "damage": 0, "chance": 0.40, "desc": "No reward."},
        ]
        self.mystery_inventory = {k: False for k in ("nuke", "water_gun", "paper_plane")}
        self.mystery_last_item: dict | None = None
        self.mystery_message: str = "Press Enter to roll (5 coins) or N for Nuke (100)."
        self.mystery_nuke_triggered = False
        self.mystery_spinning: bool = False
        self.mystery_spin_timer: float = 0.0
        self.mystery_spin_tick_timer: float = 0.0
        self.mystery_spin_duration: float = 1.5
        self.mystery_spin_tick: float = 0.1
        self.mystery_pending_item: dict | None = None

        # Game state: "main_menu", "playing", "waiting_for_customers", "collection_time", "day_over_animation", "day_over", "tax_man_notification", "tax_man", "boss_approaching", "boss_fight", "slot_machine", "mystery_box", "rain_bet"
        self.game_state = "main_menu"
        
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
        self.select_sound = None  # Select.wav sound effect
        self.menu_music_path = None  # Path to Menu.mp3 (title screen music that loops)
        self.inshop_music_path = None  # Path to InshopMusic.mp3 (in-shop music that loops)
        self.pickup_coin_sound = None  # pickupCoin.wav sound effect
        self.hit_sounds = []  # List of HitS1.wav, HitS2.wav, HitS3.wav sound effects
        self.office_music_sound = None  # Office computer sound effect (loops)
        self.tax_man_music_sound = None  # Tax man/Boss texting music (loops)
        self.boss_intro_sound = None  # Boss intro music
        
        # Room transition variables
        self.transition_active = False
        self.transition_phase = ""  # "fade_out", "flash"
        self.transition_timer = 0.0
        self.transition_duration = 0.5  # Duration for EACH phase (fade out, then flash)
        self.transition_target_room = ""
        
        # Slot machine tracking
        self.current_computer_id = 0 # 0=None, 1, 2, 3
        
        # Store reference to renderer for occasional direct access if needed
        self.renderer = None
        
        # Menu music and animation state
        self.menu_music_playing = False  # Track if menu music is playing
        self.menu_fade_out_timer = 0.0  # Timer for text fade out
        self.menu_fade_out_duration = 2.0  # Duration of fade out in seconds
        self.menu_flash_timer = 0.0  # Timer for flash effect
        self.menu_flash_duration = 0.1  # Flash duration (0.1 seconds = 100ms - very quick flash)
        
        # Tax Man flash effect
        self.tax_man_flash_timer = 0.0
        self.tax_man_flash_duration = 0.3
        self.tax_man_show_flash = False
        
        # Tax Man fade out effect
        self.tax_man_fading_out = False
        self.tax_man_fade_timer = 0.0
        self.tax_man_fade_duration = 3.0
        
        self.menu_text_alpha = 255  # Alpha value for menu text (255 = fully visible, 0 = invisible)
        self.menu_show_flash = False  # Whether to show flash effect
        
        # New Tax Man Logic variables
        self.tax_man_angered_count = 0  # How many times anger hit 100% (persists per interaction, resets daily?)
        self.tax_man_persuasion_attempts = 0  # Attempts this session
        self.tax_man_cumulative_difficulty = 0.0  # Persistent difficulty penalty for persuasion
        self.boss_fight_transition_timer = 0.0
        self.boss_fight_transition_duration = 3.0
        
        # Tax man menu state
        self.tax_man_menu_selection = 0  # 0 = Pay, 1 = Argue
        self.tax_man_ai_response: str | None = None  # Store AI response when arguing
        self.tax_man_awaiting_response = False  # Track if waiting for AI response
        self.tax_man_tax_amount = 0  # Calculate tax amount
        self.tax_man_original_tax_amount = 0  # Original tax amount before arguments
        self.tax_man_input_mode = False  # Typing disabled; only preset buttons
        self.tax_man_player_argument = ""  # Typing disabled
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
        self.tax_man_menu_locked = False  # When resolved, disable options until player closes with E
        
        # Boss fight transition (black -> white circle -> closing white bands)
        self.boss_fight_flash_timer = 0.0
        self.boss_fight_flash_duration = 2.0  # Total transition duration in seconds
        self.boss_fight_show_flash = False
        
        # Boss fight health bars (0 to 100)
        self.boss_health = 100  # Tax boss health (0-100)
        self.player_health = 100  # Player health (0-100)
        
        # Boss fight menu buttons
        # Boss fight menu selection and mode ("root" or "fight" submenu)
        self.boss_fight_menu_selection = 0
        self.boss_fight_menu_mode = "root"
        self.boss_fight_prompt_full = ""
        self.boss_fight_prompt_visible = ""
        self.boss_fight_prompt_timer = 0.0
        self.boss_fight_prompt_speed = 20.0  # chars per second (slower typing, longer prompt)
        self.boss_fight_prompt_stage = 0  # 0 = intro line, 1 = warning, 2 = ready to fight
        self.boss_fight_prompt_autoadvance_timer = 0.0  # seconds since intro prompt started
        
        # Boss approaching orange circle
        self.boss_circle_position: pygame.Vector2 | None = None  # Position of orange circle
        self.boss_circle_radius = 30.0  # Starting radius of the circle
        self.boss_circle_speed = CUSTOMER_SPEED  # Speed at which circle approaches player (same as customers)
        self.boss_circle_reached = False  # Whether circle has reached player
        self.boss_circle_path: list[pygame.Vector2] | None = None  # A* path to player
        self.boss_circle_path_index = 0  # Current waypoint index in path
        
        # Initialize AI dialogue system
        self.ai_dialogue = AIDialogue()
        
        # Combat and panic mode system
        self.panic_mode = False
        self.spawn_ban_timer = 0.0
        self.SPAWN_BAN_DURATION = (2.0 / 7.0) * DAY_DURATION  # 2 hours in 7-hour day

    def update_transition(self, dt: float) -> None:
        """Handle room transition animation."""
        self.transition_timer += dt
        
        if self.transition_phase == "fade_out":
            if self.transition_timer >= self.transition_duration:
                # Switch rooms mid-transition
                self._perform_room_switch()
                # Start flash phase
                self.transition_phase = "flash"
                self.transition_timer = 0.0
                
        elif self.transition_phase == "flash":
            if self.transition_timer >= self.transition_duration:
                # End transition
                self.transition_active = False

    def _perform_room_switch(self) -> None:
        """Execute the actual room switch logic (called mid-transition)."""
        from config import TILE_SIZE  # Ensure we have access to TILE_SIZE
        
        if self.transition_target_room == "office":
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
            
            # MUSIC: Pause shop music and play office computer sound
            try:
                pygame.mixer.music.pause()
                if self.office_music_sound:
                    self.office_music_sound.play(-1)
            except Exception as e:
                print(f"Warning: Music transition error: {e}")

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
            
            # MUSIC: Stop office sound and resume shop music
            try:
                if self.office_music_sound:
                    self.office_music_sound.stop()
                pygame.mixer.music.unpause()
            except Exception as e:
                print(f"Warning: Music transition error: {e}")

    def update(self, dt: float) -> None:
        """Update game state."""
        # Handle room transition animation
        if self.transition_active:
            self.update_transition(dt)
            return  # Block other updates during transition

        # Update slot and mystery spins even outside playing state
        self._update_slot_spin(dt)
        self._update_mystery_spin(dt)
        self._update_boss_fight_prompt(dt)
        # Auto-advance boss prompt from intro to warning after a brief pause
        if self.game_state == "boss_fight" and self.boss_fight_prompt_stage == 0:
            self.boss_fight_prompt_autoadvance_timer += dt
            if self.boss_fight_prompt_autoadvance_timer >= 3.0:
                self.boss_fight_prompt_stage = 1
                self.boss_fight_prompt_autoadvance_timer = 0.0
                self.set_boss_fight_prompt("Ima teach you to pay your taxes")

        # Handle menu fade out and flash
        if self.game_state == "main_menu":
            # Update fade out timer
            if self.menu_fade_out_timer > 0.0:
                self.menu_fade_out_timer += dt
                # Calculate alpha (fade from 255 to 0)
                progress = min(1.0, self.menu_fade_out_timer / self.menu_fade_out_duration)
                self.menu_text_alpha = int(255 * (1.0 - progress))
                
                # After fade out completes, wait 2 seconds then start flash
                # Total wait time = duration + 2.0 seconds
                if self.menu_fade_out_timer >= (self.menu_fade_out_duration + 2.0) and not self.menu_show_flash:
                    # Show flash for one frame
                    self.menu_show_flash = True
                    self.menu_flash_timer = 0.0  # Start at 0, will increment next frame
            
            # Update flash timer - wait for flash to fully fade before transitioning
            if self.menu_show_flash:
                self.menu_flash_timer += dt
                # Wait for 2x flash duration to ensure flash fully fades out before transitioning
                if self.menu_flash_timer >= self.menu_flash_duration * 2:
                    # Flash complete, transition to game IMMEDIATELY
                    # Reset all menu state first
                    self.menu_show_flash = False
                    self.menu_fade_out_timer = 0.0
                    self.menu_flash_timer = 0.0
                    self.menu_text_alpha = 255  # Reset for next time
                    # Stop menu music
                    pygame.mixer.music.stop()
                    self.menu_music_playing = False
                    # Start in-shop music
                    if self.inshop_music_path:
                        try:
                            pygame.mixer.music.load(self.inshop_music_path)
                            pygame.mixer.music.play(-1)  # Loop indefinitely
                        except Exception as e:
                            print(f"Warning: Could not load/play in-shop music: {e}")
                    # CRITICAL: Transition to game state - this must happen
                    self.game_state = "playing"
                    # Continue with update() - state change will be checked in render()
        
        # Update day timer - runs during playing and notification, pauses during tax man menu
        # Also pauses when player is in office
        if self.game_state in ("playing", "tax_man_notification") and self.current_room == "store":
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
                if self.tax_man_notification_timer >= 5.0:  # 5 seconds to respond
                    # Notification ignored - trigger boss fight next day
                    self.tax_man_boss_fight_next_day = True
                    self.tax_man_notification_timer = 0.0
                    
                    # Return to appropriate state
                    if self.day_timer >= DAY_DURATION:
                         self.game_state = "waiting_for_customers" # Or collection_time logic
                    else:
                         self.game_state = "playing" # Or continue current state?
                         
                    # Stop boss music loop if it was playing for notification?
                    # Actually notification state doesn't play boss music, usually playing state music.
                    # Just ensure we exit notification state.
                    self.game_state = "playing" 
                    pygame.mixer.music.unpause()
                # Timer continues during notification, check for day end
                if self.day_timer >= DAY_DURATION:
                    self.game_state = "waiting_for_customers"
                    # Force all customers to start leaving
                    for customer in self.customers:
                        if customer.state != "leaving":
                            customer.state = "leaving"
                            customer.path = None
                            customer.path_index = 0
        
        # Update boss approaching circle
        if self.game_state == "boss_approaching" and self.boss_circle_position is not None:
            player_pos = pygame.Vector2(self.player.x, self.player.y)
            distance_to_player = (self.boss_circle_position - player_pos).length()
            
            # Check if close enough to player to trigger boss fight
            if distance_to_player < TILE_SIZE * 0.5:  # Close enough to trigger
                if not self.boss_circle_reached:
                    self.boss_circle_reached = True
                    # Stop in-shop music and transition to boss fight with intro
                    try:
                        pygame.mixer.music.stop()
                    except Exception:
                        pass
                    if self.boss_intro_sound:
                        try:
                            self.boss_intro_sound.play()
                        except Exception as e:
                            print(f"Warning: Could not play boss intro: {e}")
                    # Transition to boss fight with flash
                    self.game_state = "boss_fight"
                    self.boss_fight_show_flash = True
                    self.boss_fight_flash_timer = 0.0
                    self.boss_fight_menu_mode = "root"
                    self.boss_fight_menu_selection = 0
                    self.boss_fight_prompt_stage = 0
                    self.boss_fight_prompt_autoadvance_timer = 0.0
                    self.set_boss_fight_prompt("Tax Dude appeared out the wild")
            else:
                # Follow A* path to player
                # Recompute path if we don't have one or if player moved significantly
                if self.boss_circle_path is None or self.boss_circle_path_index >= len(self.boss_circle_path):
                    # Compute new path to current player position
                    self.boss_circle_path = find_path(self.store_map, self.boss_circle_position, player_pos)
                    self.boss_circle_path_index = 0
                
                # Follow the path
                if self.boss_circle_path and len(self.boss_circle_path) > 0 and self.boss_circle_path_index < len(self.boss_circle_path):
                    # Get current waypoint
                    next_waypoint = self.boss_circle_path[self.boss_circle_path_index]
                    distance_to_waypoint = (self.boss_circle_position - next_waypoint).length()
                    
                    # Check if we've reached the waypoint
                    waypoint_threshold = TILE_SIZE * 0.5
                    if distance_to_waypoint < waypoint_threshold:
                        # Reached waypoint, move to next
                        self.boss_circle_path_index += 1
                        if self.boss_circle_path_index < len(self.boss_circle_path):
                            next_waypoint = self.boss_circle_path[self.boss_circle_path_index]
                    
                    # Move towards current waypoint (use same timing as customers)
                    direction = next_waypoint - self.boss_circle_position
                    if direction.length() > 0:
                        direction.normalize_ip()
                        # Use same movement calculation as customers: speed * dt * FPS
                        step = self.boss_circle_speed * dt * FPS
                        movement = direction * step
                        self.boss_circle_position += movement
                else:
                    # No path available, fall back to direct movement (use same timing as customers)
                    direction = player_pos - self.boss_circle_position
                    if direction.length() > 0:
                        direction.normalize_ip()
                        # Use same movement calculation as customers: speed * dt * FPS
                        step = self.boss_circle_speed * dt * FPS
                        movement = direction * step
                        self.boss_circle_position += movement
        
        # Update boss fight flash timer
        if self.game_state == "boss_fight" and self.boss_fight_show_flash:
            self.boss_fight_flash_timer += dt
            if self.boss_fight_flash_timer >= self.boss_fight_flash_duration:
                self.boss_fight_show_flash = False
        
        # Check persuasion after AI response is received (in main thread)
        if self.game_state == "tax_man" and not self.tax_man_awaiting_response and not self.tax_man_has_paid:
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
        
        # Update tax man flash timer
        if self.game_state == "tax_man" and self.tax_man_show_flash:
            self.tax_man_flash_timer += dt
            if self.tax_man_flash_timer >= self.tax_man_flash_duration:
                self.tax_man_show_flash = False
        
        # Update tax man fade out
        if self.game_state == "tax_man" and self.tax_man_fading_out:
            self.tax_man_fade_timer += dt
            if self.tax_man_fade_timer >= self.tax_man_fade_duration:
                # Fade complete - close phone
                self.tax_man_fading_out = False
                self.tax_man_fade_timer = 0.0
                
                # Stop boss music and resume game music
                if self.tax_man_music_sound:
                    self.tax_man_music_sound.stop()
                pygame.mixer.music.unpause()
                
                # Return to playing
                self.game_state = "playing"
        
                # Return to playing
                self.game_state = "playing"
                
        # Only update game logic if we're in a state that allows gameplay
        if self.game_state not in ("playing", "waiting_for_customers", "collection_time", "tax_man_notification", "boss_approaching"):
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
                # Play pickup coin sound
                if self.pickup_coin_sound is not None:
                    try:
                        self.pickup_coin_sound.play()
                    except Exception as e:
                        print(f"Warning: Could not play pickup coin sound: {e}")

        # Remove collected dodge coins
        for coin in coins_to_remove:
            if coin in self.cash_items:
                self.cash_items.remove(coin)

        # Update spawn ban timer and panic mode (only in store)
        if self.spawn_ban_timer > 0.0 and self.current_room == "store":
            self.spawn_ban_timer -= dt
            if self.spawn_ban_timer <= 0.0:
                self.spawn_ban_timer = 0.0
                self.panic_mode = False
        
        # Only update store entities when in store room
        if self.current_room == "store":
            # Spawn customers (only during playing state, and not during spawn ban)
            if self.game_state == "playing":
                spawn_ban_active = self.spawn_ban_timer > 0.0
                new_customer = self.spawner.update(dt, self.customers, spawn_ban_active=spawn_ban_active)
                if new_customer:
                    self.customers.append(new_customer)

            # Update customers
            for customer in self.customers:
                customer_obstacle_rects, customer_door_rects = get_customer_solid_tiles_around(customer.rect, self.tile_map)
                # Customers only collide with obstacles, NOT doors (they phase through doors)
                # Door rects are passed separately but not used for collision
                
                # Handle different customer types
                # Use player speed if in panic mode
                use_player_speed = self.panic_mode
                
                if isinstance(customer, ThiefCustomer):
                    # Thief customer needs access to dodge coins to find targets
                    customer.update(dt, customer_obstacle_rects, self.cash_items, customer_door_rects, use_player_speed=use_player_speed)
                    if customer.stole_cash and customer.target_cash:
                        # Remove the stolen dodge coin
                        if customer.target_cash in self.cash_items:
                            self.cash_items.remove(customer.target_cash)
                        customer.stole_cash = False
                        customer.target_cash = None
                elif isinstance(customer, LitterCustomer):
                    # Litter customer drops litter
                    customer.update(dt, customer_obstacle_rects, customer_door_rects, use_player_speed=use_player_speed)
                    if customer.drop_litter and customer.litter_pos:
                        # Place litter where customer dropped it
                        self.litter_items.append(Litter(customer.litter_pos))
                        customer.drop_litter = False
                        customer.litter_pos = None
                else:
                    # Regular customer drops dodge coins
                    customer.update(dt, customer_obstacle_rects, customer_door_rects, use_player_speed=use_player_speed)
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
                # Transition to animation state
                self.game_state = "day_over_animation"
                self.day_over_animation_progress = 0.0
                self.video_playing = True  # Signal that video should start playing
                
                # Stop in-shop music
                pygame.mixer.music.stop()
                # Stop office music if playing
                if self.office_music_sound:
                    self.office_music_sound.stop()
                
                # Play day over music
                try:
                    pygame.mixer.music.load("assets/sounds/Dayover.mp3")
                    pygame.mixer.music.play()
                except Exception as e:
                    print(f"Warning: Could not play day over music: {e}")

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
                # Block input if fading out
                if self.tax_man_fading_out:
                    return True
                # Block clicks when menu is locked (after paying or anger trigger)
                if self.tax_man_menu_locked:
                    return True

                mouse_pos = event.pos
                
                # Check side buttons first
                clicked_button = renderer.get_tax_side_button_clicked(mouse_pos)
                if clicked_button:
                    if clicked_button == "Pay":
                        return self._pay_tax()
                    elif clicked_button == "Valid Excuse":
                        return self._send_player_message(self._get_preset_message("Valid Excuse"))
                    elif clicked_button == "Argue":
                        return self._send_player_message(self._get_preset_message("Argue"))
                    elif clicked_button == "Romance":
                        return self._send_player_message(self._get_preset_message("Romance"))
                        
                # Check Venmo bubble
                elif renderer.is_venmo_bubble_clicked(mouse_pos):
                    return self._pay_tax()

        elif event.type == pygame.KEYDOWN:
            # Slot machine input handling
            if self.game_state == "slot_machine":
                if self.slot_spinning:
                    return False
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_e:
                    self._exit_slot_machine()
                    return False
                if event.key == pygame.K_RETURN:
                    self._spin_slot_machine()
                    return False
                if event.key in (pygame.K_w, pygame.K_UP):
                    if self.slot_bet < self.collected_coins:
                        self.slot_bet += 1
                    return False
                if event.key in (pygame.K_s, pygame.K_DOWN):
                    if self.slot_bet > 0:
                        self.slot_bet -= 1
                    return False
                return False
            # Rain Bet (Computer 3) input handling
            if self.game_state == "rain_bet":
                if event.key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                    self._exit_rain_bet()
                    return False
                return False
            # Mystery box (Computer 2) input handling
            if self.game_state == "mystery_box":
                if self.mystery_spinning:
                    return False
                if self.mystery_nuke_triggered:
                    if event.key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                        self._exit_mystery_box(end_game=True)
                    return False
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_e:
                    self._exit_mystery_box()
                    return False
                if event.key == pygame.K_RETURN:
                    self._roll_mystery_box()
                    return False
                if event.key == pygame.K_n:
                    self._buy_guaranteed_nuke()
                    return False
                return False
            if event.key == pygame.K_ESCAPE:
                return True
            # Handle main menu input
            if self.game_state == "main_menu":
                # Any key or Enter starts the fade out sequence
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE or event.key == pygame.K_p:
                    # Play select sound
                    if self.select_sound is not None:
                        try:
                            self.select_sound.play()
                        except Exception as e:
                            print(f"Warning: Could not play select sound: {e}")
                    
                    # Fade out menu music over 2 seconds (matching text fade)
                    pygame.mixer.music.fadeout(2000)
                    self.menu_music_playing = False
                    
                    # Start fade out (don't transition to playing yet - update() will handle it)
                    if self.menu_fade_out_timer == 0.0:  # Only start if not already fading
                        self.menu_fade_out_timer = 0.001  # Start timer (small value to begin fade)
                    return False
            # Check interactions when 'e' is pressed
            if event.key == pygame.K_e:
                if self.game_state == "playing" and self.current_room == "office":
                    tile = self._get_player_tile()
                    if tile == TILE_ACTIVATION_1:
                        # Enter slot machine (only on Computer 1)
                        self._start_slot_machine()
                        return False
                    elif tile == TILE_ACTIVATION_2:
                        # Enter mystery box (Computer 2)
                        self._start_mystery_box()
                        return False
                    elif tile == TILE_ACTIVATION_3:
                        # Enter Rain Bet (Computer 3)
                        self._start_rain_bet()
                        return False
            
            # Debug: Press P to open tax man phone at any time
            if event.key == pygame.K_p and self.game_state == "playing":
                self.game_state = "tax_man"
                # Start flash effect
                self.tax_man_show_flash = True
                self.tax_man_flash_timer = 0.0
                # Initialize tax amount if 0
                if self.tax_man_tax_amount == 0:
                    self.tax_man_tax_amount = max(1, int(self.collected_coins * 0.1))
                    self.tax_man_original_tax_amount = self.tax_man_tax_amount
                
                # Pause game music and play boss music
                pygame.mixer.music.pause()
                if self.tax_man_music_sound:
                    self.tax_man_music_sound.play(-1)
                return False
            # Handle SPACE key for attacking customers
            if event.key == pygame.K_SPACE:
                if self.game_state == "playing" and self.current_room == "store":
                    self._handle_player_attack()
                    return False
            # Handle "O" key to activate boss fight anytime
            if event.key == pygame.K_o:
                if self.game_state == "playing":
                    # Start with orange circle approaching instead of immediate boss fight
                    self.game_state = "boss_approaching"
                    # Initialize circle position at door (like a customer)
                    door_centers = self.store_map.find_tile_centers("D")  # TILE_DOOR
                    door_pos = door_centers[0] if door_centers else pygame.Vector2(
                        self.store_map.cols * TILE_SIZE // 2,
                        self.store_map.rows * TILE_SIZE // 2
                    )
                    self.boss_circle_position = pygame.Vector2(door_pos)
                    self.boss_circle_radius = 30.0
                    self.boss_circle_reached = False
                    self.boss_circle_path = None
                    self.boss_circle_path_index = 0
                    # Compute path to player
                    player_pos = pygame.Vector2(self.player.x, self.player.y)
                    self.boss_circle_path = find_path(self.store_map, self.boss_circle_position, player_pos)
                    self.boss_circle_path_index = 0
                    return False
                elif self.game_state == "boss_fight":
                    # Exit boss fight and return to playing
                    self.game_state = "playing"
                    self.boss_fight_show_flash = False
                    self.boss_fight_flash_timer = 0.0
                    return False
            elif self.game_state == "boss_fight":
                # Handle menu navigation in boss fight
                if event.key == pygame.K_w or event.key == pygame.K_UP:
                    # Move selection up
                    max_index = 3 if self.boss_fight_menu_mode == "fight" else 2
                    prev_selection = self.boss_fight_menu_selection
                    self.boss_fight_menu_selection = max(0, self.boss_fight_menu_selection - 1)
                    self.boss_fight_menu_selection = min(self.boss_fight_menu_selection, max_index)
                    if self.select_sound and self.boss_fight_menu_selection != prev_selection:
                        try:
                            self.select_sound.play()
                        except Exception as e:
                            print(f"Warning: Could not play select sound: {e}")
                    return False
                elif event.key == pygame.K_s or event.key == pygame.K_DOWN:
                    max_index = 3 if self.boss_fight_menu_mode == "fight" else 2
                    prev_selection = self.boss_fight_menu_selection
                    self.boss_fight_menu_selection = min(max_index, self.boss_fight_menu_selection + 1)
                    if self.select_sound and self.boss_fight_menu_selection != prev_selection:
                        try:
                            self.select_sound.play()
                        except Exception as e:
                            print(f"Warning: Could not play select sound: {e}")
                    return False
                elif event.key == pygame.K_RETURN:
                    # Enter fight submenu from root when Fight is selected
                    if (
                        self.boss_fight_menu_mode == "root"
                        and self.boss_fight_menu_selection == 0
                        and self.boss_fight_prompt_stage >= 2
                    ):
                        self.boss_fight_menu_mode = "fight"
                        self.boss_fight_menu_selection = 0
                        return False
                elif event.key == pygame.K_SPACE:
                    if self.boss_fight_menu_mode == "root":
                        if self.boss_fight_prompt_stage in (0, 1):
                            # Open fight menu and show move prompt
                            self.boss_fight_prompt_stage = 2
                            self.boss_fight_prompt_autoadvance_timer = 0.0
                            self.boss_fight_menu_mode = "fight"
                            self.boss_fight_menu_selection = 0
                            self.set_boss_fight_prompt("Select your move.")
                            return False
                        else:
                            # Already ready; no action
                            return False
                elif event.key in (pygame.K_ESCAPE, pygame.K_e):
                    # If in fight submenu, go back to root; otherwise ignore (can't exit)
                    if self.boss_fight_menu_mode == "fight":
                        self.boss_fight_menu_mode = "root"
                        self.boss_fight_menu_selection = 0
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
                # E key opens tax man menu from notification
                if event.key == pygame.K_e:
                    self.game_state = "tax_man"
                    self.tax_man_menu_selection = 0
                    self.tax_man_ai_response = None
                    self.tax_man_awaiting_response = False
                    self.tax_man_input_mode = True
                    self.tax_man_player_argument = ""
                    self.tax_man_conversation = []
                    # Reset notification timer when opening menu
                    self.tax_man_notification_timer = 0.0
                    # Start flash effect
                    self.tax_man_show_flash = True
                    self.tax_man_flash_timer = 0.0
                    
                    # Pause game music and play boss music
                    pygame.mixer.music.pause()
                    if self.tax_man_music_sound:
                        self.tax_man_music_sound.play(-1)
            elif self.game_state == "tax_man":
                # E key closes tax man screen (can close anytime)
                if event.key == pygame.K_e:
                    # Check if player has paid - if not, trigger boss fight next day
                    if not self.tax_man_has_paid:
                        # Player closed without paying - trigger boss fight next day
                        self.tax_man_boss_fight_next_day = True
                        self.tax_man_boss_fight_triggered = True
                    # Close phone and return to gameplay
                    self.game_state = "playing"
                    self._reset_tax_man_state()
                    
                    # Stop boss music and resume game music
                    if self.tax_man_music_sound:
                        self.tax_man_music_sound.stop()
                    pygame.mixer.music.unpause()
                    
                    return False
                
                # When menu is locked (paid or boss fight triggered), ignore other input
                if self.tax_man_menu_locked:
                    return False
                # Handle chat input in tax man screen (only if boss fight not triggered)
                if not self.tax_man_boss_fight_triggered:
                    # Block input if fading out
                    if self.tax_man_fading_out:
                        return False

                    # Navigation keys for sidebar (W/S/UP/DOWN)
                    if event.key in (pygame.K_w, pygame.K_UP):
                        self.tax_man_menu_selection = (self.tax_man_menu_selection - 1) % 4
                        if self.select_sound:
                            self.select_sound.play()
                        return False
                    elif event.key in (pygame.K_s, pygame.K_DOWN):
                        self.tax_man_menu_selection = (self.tax_man_menu_selection + 1) % 4
                        if self.select_sound:
                            self.select_sound.play()
                        return False
                        
                    if event.key == pygame.K_RETURN:
                        # Activate the selected side button (no typing)
                        idx = self.tax_man_menu_selection
                        if idx == 0: # Valid Excuse
                            return self._send_player_message(self._get_preset_message("Valid Excuse"), category="Valid Excuse")
                        elif idx == 1: # Argue
                            return self._send_player_message(self._get_preset_message("Argue"), category="Argue")
                        elif idx == 2: # Romance
                            return self._send_player_message(self._get_preset_message("Romance"), category="Romance")
                        elif idx == 3: # Pay
                            return self._pay_tax()
        return False

    def _handle_player_attack(self) -> None:
        """Handle player attack - check collision with customers and deal damage."""
        player_rect = self.player.rect
        player_pos = pygame.Vector2(self.player.x, self.player.y)
        
        customers_to_remove = []
        for customer in self.customers:
            # Check collision between player and customer
            if player_rect.colliderect(customer.rect):
                # Play random hit sound
                if self.hit_sounds:
                    import random
                    sound = random.choice(self.hit_sounds)
                    try:
                        sound.play()
                    except Exception as e:
                        print(f"Warning: Could not play hit sound: {e}")
                
                # Calculate knockback direction (away from player)
                knockback_direction = customer.position - player_pos
                if knockback_direction.length_squared() > 0:
                    knockback_direction.normalize_ip()
                else:
                    # If customer is exactly on player, use random direction
                    angle = random.uniform(0, 2 * 3.14159)
                    knockback_direction = pygame.Vector2(math.cos(angle), math.sin(angle))
                
                # Apply knockback (quarter of a tile - 2x weaker than before)
                knockback_force = TILE_SIZE * 0.25
                customer.apply_knockback(knockback_direction, knockback_force)
                
                # Deal 1 damage
                is_dead = customer.take_damage(1)
                
                if is_dead:
                    # Handle customer death
                    # Check if this is a regular Customer (not ThiefCustomer or LitterCustomer)
                    was_regular = isinstance(customer, Customer) and not isinstance(customer, ThiefCustomer) and not isinstance(customer, LitterCustomer)
                    customers_to_remove.append((customer, was_regular))
                else:
                    # If hit but not dead, customer should flee (state = "leaving")
                    if customer.state != "leaving":
                        customer.state = "leaving"
                        customer.path = None
                        customer.path_index = 0
                        if hasattr(customer, 'leave_pos'):
                            customer._compute_path(customer.leave_pos)
        
        # Handle customer deaths
        for customer, was_regular in customers_to_remove:
            self._handle_customer_death(customer, was_regular)
    
    def _handle_customer_death(self, customer, was_regular: bool) -> None:
        """
        Handle customer death - drop cash and trigger panic mode if regular customer.
        
        Args:
            customer: The customer that died
            was_regular: True if this was a regular Customer (not ThiefCustomer or LitterCustomer)
        """
        # Drop cash at customer position (regardless of type)
        from entities import Cash
        self.cash_items.append(Cash(customer.position))
        
        # Remove customer from list
        if customer in self.customers:
            self.customers.remove(customer)
        
        # If was regular customer, trigger panic mode
        if was_regular:
            self.panic_mode = True
            self.spawn_ban_timer = self.SPAWN_BAN_DURATION
            
            # Force all customers to flee at player speed
            for other_customer in self.customers:
                if other_customer.state != "leaving":
                    other_customer.state = "leaving"
                    other_customer.path = None
                    other_customer.path_index = 0
                    if hasattr(other_customer, 'leave_pos'):
                        other_customer._compute_path(other_customer.leave_pos)
    
    def _start_new_day(self) -> None:
        """Reset game state for a new day."""
        self.current_day += 1
        self.day_timer = 0.0
        
        # Reset panic mode and spawn ban
        self.panic_mode = False
        self.spawn_ban_timer = 0.0
        # Clear all uncollected dodge coins
        self.cash_items.clear()
        # Clear all customers
        self.customers.clear()
        # Clear all litter
        self.litter_items.clear()
        
        # Check if boss fight should happen this day
        if self.tax_man_boss_fight_next_day:
            # Start with orange circle approaching instead of immediate boss fight
            self.game_state = "boss_approaching"
            # Initialize circle position at door (like a customer)
            door_centers = self.store_map.find_tile_centers("D")  # TILE_DOOR
            door_pos = door_centers[0] if door_centers else pygame.Vector2(
                self.store_map.cols * TILE_SIZE // 2,
                self.store_map.rows * TILE_SIZE // 2
            )
            self.boss_circle_position = pygame.Vector2(door_pos)
            self.boss_circle_radius = 30.0
            self.boss_circle_reached = False
            self.boss_circle_path = None
            self.boss_circle_path_index = 0
            # Compute path to player
            player_pos = pygame.Vector2(self.player.x, self.player.y)
            self.boss_circle_path = find_path(self.store_map, self.boss_circle_position, player_pos)
            self.boss_circle_path_index = 0
            self.tax_man_boss_fight_next_day = False  # Reset flag
            self.boss_fight_menu_mode = "root"
            self.boss_fight_menu_selection = 0
            self.boss_fight_prompt_stage = 0
            self.boss_fight_prompt_autoadvance_timer = 0.0
            self.set_boss_fight_prompt("Tax Dude appeared out the wild")
            # Keep in-shop music playing during approach
            if self.inshop_music_path:
                try:
                    pygame.mixer.music.load(self.inshop_music_path)
                    pygame.mixer.music.play(-1)
                except Exception as e:
                    print(f"Warning: Could not load/play in-shop music during boss approach: {e}")
        else:
            # Reset game state to playing
            self.game_state = "playing"
            # Start in-shop music if not already playing
            if self.inshop_music_path:
                try:
                    pygame.mixer.music.load(self.inshop_music_path)
                    pygame.mixer.music.play(-1)  # Loop indefinitely
                except Exception as e:
                    print(f"Warning: Could not load/play in-shop music: {e}")
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
        self.tax_man_menu_locked = False  # Unlock menu for new day
        if hasattr(self, '_last_persuasion_check_index'):
            self._last_persuasion_check_index = -1

    def _check_persuasion(self) -> None:
        """Check if player successfully persuades the tax man."""
        import random
        
        # Calculate persuasion chance (only if AI dialogue is available)
        if self.ai_dialogue:
            persuasive = self.ai_dialogue.check_persuasion(self.tax_man_ai_response)
            
            if persuasive:
                # Calculate persuasion chance based on new rules
                import random
                
                base_chance = 0.0
                
                # First attempt: 70% chance
                if self.tax_man_persuasion_attempts == 0:
                    base_chance = 0.70
                else:
                    # Subsequent attempts: 0-50% based on anger (linear scaling)
                    anger_factor = max(0.0, 1.0 - (self.tax_man_anger / 100.0))
                    base_chance = 0.5 * anger_factor
                
                # Apply cumulative difficulty penalty
                final_chance = max(0.0, base_chance - self.tax_man_cumulative_difficulty)
                
                # Roll dice
                if random.random() < final_chance:
                    # Persuaded!
                    self.tax_man_has_paid = True  # Treat as paid (let go)
                    
                    # Avoid double boss messages: only add one if none exists or last isn't boss
                    if not self.tax_man_conversation or self.tax_man_conversation[-1].get("sender") != "boss":
                        self.tax_man_conversation.append({
                            "sender": "boss",
                            "message": "Fine. Paid. Don't test me again."
                        })
                    
                    # Increase difficulty for next time (capped at 20%)
                    self.tax_man_cumulative_difficulty = min(0.20, self.tax_man_cumulative_difficulty + 0.05)
                    
                    # Lock menu; player can close manually with E
                    self.tax_man_menu_locked = True
                
            # Increment attempts counter regardless of success/fail (if it was persuasive enough to check mechanics)
            self.tax_man_persuasion_attempts += 1

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
        self.tax_man_fading_out = False
        self.tax_man_fade_timer = 0.0
        self.tax_man_menu_locked = False
        
        # Reset new logic variables (per session)
        self.tax_man_angered_count = 0
        self.tax_man_persuasion_attempts = 0
        # tax_man_cumulative_difficulty is NOT reset here (persistent)
        
        if hasattr(self, '_last_persuasion_check_index'):
            self._last_persuasion_check_index = -1

    def get_boss_fight_options(self) -> list[dict]:
        """Return boss fight option list with availability."""
        return [
            {"label": "Logic", "enabled": True},
            {"label": "Nuke", "enabled": self.mystery_inventory.get("nuke", False)},
            {"label": "Water Gun", "enabled": self.mystery_inventory.get("water_gun", False)},
            {"label": "Paper Plane", "enabled": self.mystery_inventory.get("paper_plane", False)},
        ]
    
    def get_boss_root_options(self) -> list[dict]:
        """Root menu options before entering fight submenu."""
        return [
            {"label": "Fight", "enabled": True},
            {"label": "Bag", "enabled": False},
            {"label": "Pay", "enabled": False},
        ]

    def set_boss_fight_prompt(self, text: str, speed: float | None = None) -> None:
        """Set the boss fight prompt text and reset typing effect."""
        self.boss_fight_prompt_full = text or ""
        self.boss_fight_prompt_visible = ""
        self.boss_fight_prompt_timer = 0.0
        if speed is not None:
            self.boss_fight_prompt_speed = speed

    def _update_boss_fight_prompt(self, dt: float) -> None:
        """Update typing effect for boss fight prompt."""
        if self.game_state != "boss_fight":
            return
        if not self.boss_fight_prompt_full:
            self.boss_fight_prompt_visible = ""
            return
        self.boss_fight_prompt_timer += dt
        chars = int(self.boss_fight_prompt_timer * self.boss_fight_prompt_speed)
        self.boss_fight_prompt_visible = self.boss_fight_prompt_full[:chars]

    def _get_player_tile(self) -> str:
        """Return the tile code currently under the player."""
        player_col = int(self.player.x // TILE_SIZE)
        if self.current_room == "office":
            player_local_y = self.player.y - self.office_world_y_offset
            player_row = int(player_local_y // TILE_SIZE)
        else:
            player_row = int(self.player.y // TILE_SIZE)
        return self.tile_map.tile_at(player_col, player_row)

    def _start_mystery_box(self) -> None:
        """Enter the Computer 2 mystery box screen."""
        self.game_state = "mystery_box"
        self.current_computer_id = 2
        self.mystery_message = "Press Enter to roll (5 coins) or N for Nuke (100)."
        self.mystery_last_item = None
        self.mystery_nuke_triggered = False
        self.mystery_spinning = False
        self.mystery_pending_item = None
        self.mystery_spin_timer = 0.0
        self.mystery_spin_tick_timer = 0.0

    def _exit_mystery_box(self, end_game: bool = False) -> None:
        """Leave the mystery box screen back to gameplay or game over."""
        self.mystery_spinning = False
        self.mystery_pending_item = None
        if end_game:
            self.game_state = "day_over"
        else:
            self.game_state = "playing"
        self.current_computer_id = 0
        # Reset prompt so next entry starts fresh
        self.mystery_message = "Press Enter to roll (5 coins) or N for Nuke (100)."

    def _choose_mystery_item(self) -> dict:
        """Randomly choose an item based on configured chances."""
        roll = random.random()
        cumulative = 0.0
        for item in self.mystery_items:
            cumulative += item["chance"]
            if roll <= cumulative:
                return item
        return self.mystery_items[-1]

    def _apply_mystery_item(self, item: dict) -> None:
        """Apply the outcome of a mystery box pull."""
        self.mystery_last_item = item
        key = item["key"]

        if key == "nothing":
            self.mystery_message = "Nothing happened."
            return

        already_owned = self.mystery_inventory.get(key, False)
        if already_owned:
            self.mystery_message = f"Already have {item['name']}."
        else:
            self.mystery_inventory[key] = True
            self.mystery_message = f"Got {item['name']} ({item['damage']} dmg)."

        if key == "nuke":
            # Trigger game over effect
            self.mystery_nuke_triggered = True
            self.mystery_message = "Nuke pulled! Game over."

    def _roll_mystery_box(self) -> None:
        """Resolve a mystery box roll (Computer 2)."""
        if self.mystery_nuke_triggered:
            return
        if self.mystery_spinning:
            return
        cost = 5
        if self.collected_coins < cost:
            self.mystery_message = "Need 5 coins to roll."
            return

        self.collected_coins -= cost
        item = self._choose_mystery_item()
        self.mystery_pending_item = item
        self.mystery_spinning = True
        self.mystery_spin_timer = 0.0
        self.mystery_spin_tick_timer = 0.0
        self.mystery_message = "Spinning..."
        self.mystery_last_item = None

    def _buy_guaranteed_nuke(self) -> None:
        """Purchase a guaranteed nuke outcome for 100 coins."""
        if self.mystery_nuke_triggered:
            return
        if self.mystery_spinning:
            return

        cost = 100
        if self.collected_coins < cost:
            self.mystery_message = "Need 100 coins for Nuke."
            return

        self.collected_coins -= cost
        nuke_item = next((i for i in self.mystery_items if i["key"] == "nuke"), None)
        if nuke_item:
            self.mystery_pending_item = nuke_item
            self.mystery_spinning = True
            self.mystery_spin_timer = 0.0
            self.mystery_spin_tick_timer = 0.0
            self.mystery_message = "Spinning..."
            self.mystery_last_item = None

    def _update_mystery_spin(self, dt: float) -> None:
        """Animate mystery box spin and resolve pending item."""
        if not self.mystery_spinning:
            return

        self.mystery_spin_timer += dt
        self.mystery_spin_tick_timer += dt

        # Cycle preview symbol
        preview_keys = ["nuke", "water_gun", "paper_plane", "nothing"]
        if self.mystery_spin_tick_timer >= self.mystery_spin_tick:
            self.mystery_spin_tick_timer = 0.0
            preview_key = random.choice(preview_keys)
            self.mystery_last_item = {"key": preview_key}

        if self.mystery_spin_timer >= self.mystery_spin_duration:
            if self.mystery_pending_item:
                self._apply_mystery_item(self.mystery_pending_item)
            self.mystery_pending_item = None
            self.mystery_spinning = False
            self.mystery_spin_timer = 0.0
            self.mystery_spin_tick_timer = 0.0

    def _start_rain_bet(self) -> None:
        """Enter the Computer 3 Rain Bet screen."""
        self.game_state = "rain_bet"
        self.current_computer_id = 3

    def _exit_rain_bet(self) -> None:
        """Leave the Rain Bet screen back to gameplay."""
        self.game_state = "playing"
        self.current_computer_id = 0

    def _start_slot_machine(self) -> None:
        """Enter the slot machine screen."""
        self.game_state = "slot_machine"
        self.slot_bet = 0
        self.slot_message = "Enter bet and press Enter."
        self.slot_reels = ["♠", "♥", "♦"]
        self.slot_spinning = False
        self.slot_spin_result = None
        self.slot_spin_timer = 0.0
        self.slot_spin_tick_timer = 0.0
        self.slot_current_bet = 0
        
        # Determine which computer was activated
        tile = self._get_player_tile()
        from config import TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3
        if tile == TILE_ACTIVATION_1:
            self.current_computer_id = 1
        elif tile == TILE_ACTIVATION_2:
            self.current_computer_id = 2
        elif tile == TILE_ACTIVATION_3:
            self.current_computer_id = 3
        else:
            self.current_computer_id = 0

    def _exit_slot_machine(self) -> None:
        """Leave the slot machine screen back to gameplay."""
        self.game_state = "playing"
        self.slot_bet = 0
        self.slot_message = "Enter bet and press Enter."
        self.slot_spinning = False
        self.slot_spin_result = None
        self.slot_current_bet = 0

    def _spin_slot_machine(self) -> None:
        """Resolve a slot spin with."""
        # Guard against empty balance
        if self.collected_coins <= 0:
            self.slot_message = "Not enough coins to bet."
            return

        bet_value = min(self.slot_bet, self.collected_coins)
        if bet_value <= 0:
            self.slot_message = "Bet must be greater than 0."
            return

        # Take the bet and start spinning animation
        self.collected_coins -= bet_value
        self.slot_current_bet = bet_value
        symbols = ["♠", "♥", "♦", "♣"]
        symbol_payouts = {"♠": 5, "♥": 4, "♦": 3, "♣": 2}
        win = random.random() < 0.30
        chosen_symbol = random.choice(symbols) if win else None
        self.slot_spin_result = {
            "win": win,
            "symbol": chosen_symbol,
            "payouts": symbol_payouts,
            "symbols": symbols,
        }
        self.slot_spinning = True
        self.slot_spin_timer = 0.0
        self.slot_spin_tick_timer = 0.0
        self.slot_message = "Spinning..."

    def _update_slot_spin(self, dt: float) -> None:
        """Animate slot spinning and resolve when duration ends."""
        if not self.slot_spinning:
            return

        self.slot_spin_timer += dt
        self.slot_spin_tick_timer += dt

        symbols = self.slot_spin_result.get("symbols", ["♠", "♥", "♦", "♣"]) if self.slot_spin_result else ["♠", "♥", "♦", "♣"]

        # Shuffle reels periodically for visual spin
        if self.slot_spin_tick_timer >= self.slot_spin_tick:
            self.slot_spin_tick_timer = 0.0
            self.slot_reels = [random.choice(symbols) for _ in range(3)]

        if self.slot_spin_timer >= self.slot_spin_duration:
            # Finish spin
            result = self.slot_spin_result or {}
            win = result.get("win", False)
            symbol = result.get("symbol", random.choice(symbols))
            symbol_payouts = result.get("payouts", {"♠": 5, "♥": 4, "♦": 3, "♣": 2})
            bet_value = self.slot_current_bet

            if win and bet_value > 0:
                self.slot_reels = [symbol, symbol, symbol]
                multiplier = symbol_payouts.get(symbol, 2)
                payout = bet_value * multiplier
                self.collected_coins += payout
                self.slot_message = f"WIN! {symbol*3} x{multiplier}: +{payout} coins"
            else:
                # Generate a non-matching mix to show loss
                loss_reels = [random.choice(symbols) for _ in range(3)]
                if len(set(loss_reels)) == 1:
                    alt = random.choice([s for s in symbols if s != loss_reels[0]])
                    loss_reels[0] = alt
                self.slot_reels = loss_reels
                self.slot_message = "Lost. Try again?"

            # Clamp bet to current coins after spin
            self.slot_bet = min(self.slot_bet, self.collected_coins)
            # Reset spin state
            self.slot_spinning = False
            self.slot_spin_result = None
            self.slot_current_bet = 0
            self.slot_spin_timer = 0.0
            self.slot_spin_tick_timer = 0.0

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
            # Start transition sequence
            self.transition_active = True
            self.transition_phase = "fade_out"
            self.transition_timer = 0.0
            
            # Determine target room
            if self.current_room == "store":
                self.transition_target_room = "office"
            else:
                self.transition_target_room = "store"
        
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


    def _pay_tax(self) -> bool:
        """
        Attempt to pay the tax.
        Returns False to indicate event callback handled (even if payment failed).
        """
        # Guard against double payment
        if self.tax_man_has_paid:
            return False

        # Check if player can pay
        if self.collected_coins >= self.tax_man_tax_amount:
            # Pay tax
            self.collected_coins = max(0, self.collected_coins - self.tax_man_tax_amount)
            self.tax_man_has_paid = True
            # Lock menu; player can close manually with E
            self.tax_man_menu_locked = True
            return False
        else:
            # Can't pay - trigger boss fight next day
            self.tax_man_boss_fight_next_day = True
            self.tax_man_boss_fight_triggered = True
            self.tax_man_menu_locked = True
            # Show a message explaining the consequence if one is not already present
            if not self.tax_man_conversation or self.tax_man_conversation[-1].get("sender") != "boss":
                self.tax_man_conversation.append({
                    "sender": "boss",
                    "message": "No payment? Then we settle this tomorrow."
                })
            return False

    def _send_player_message(self, message: str, category: str = "Argue") -> bool:
        """
        Send a message from the player to the boss.
        
        Args:
            message: Content of the message
            
        Returns:
            False (to indicate event handled)
        """
        if not message.strip():
            return False

        player_msg = message.strip()
        
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
            # Trigger fade out
            self.tax_man_fading_out = True
            self.tax_man_fade_timer = 0.0
            return False
        
        if self.tax_man_anger == 0.0:
            self.tax_man_anger = 20.0
        
        # Increase anger by 5-15% per message
        import random
        anger_increase = random.uniform(5.0, 15.0)
        self.tax_man_anger = min(100.0, self.tax_man_anger + anger_increase)
        
        # Add player message to conversation immediately
        self.tax_man_conversation.append({
            "sender": "player",
            "message": player_msg
        })
        
        # Check if anger reached 100%
        if self.tax_man_anger >= 100.0:
            self.tax_man_angered_count += 1
            
            # Scenario 1: First time triggering 100% anger (Seniority 1)
            if self.tax_man_angered_count == 1:
                # Prompt with new venmo + 1 original
                self.tax_man_tax_amount = self.tax_man_original_tax_amount + 1
                self.tax_man_conversation.append({
                    "sender": "boss",
                    "message": "You're testing my patience. Price just went up. Pay now."
                })
                # Reset anger to 20% to allow trying again (but harder to persuade now ideally, though difficulty is on persuasion success)
                self.tax_man_anger = 20.0
                return False
                
            # Scenario 2: Second time triggering 100% anger (Seniority 2) -> BOSS FIGHT
            else:
                self.tax_man_conversation.append({
                    "sender": "boss",
                    "message": "That's it. Only one way to settle this."
                })
                # Trigger boss fight next day (original behavior)
                self.tax_man_boss_fight_next_day = True
                self.tax_man_boss_fight_triggered = True
                # Lock menu; player can close manually with E
                self.tax_man_menu_locked = True
                return False
        
        # Set awaiting response flag
        self.tax_man_awaiting_response = True
        
        # Choose a boss response (funny, coherent mob-boss tone)
        boss_response = self._get_boss_response(category=category, anger=self.tax_man_anger)
        self.tax_man_conversation.append({
            "sender": "boss",
            "message": boss_response
        })
        self.tax_man_ai_response = boss_response  # Used by persuasion logic
        self.tax_man_awaiting_response = False
        return False

    def _get_preset_message(self, category: str) -> str:
        """Get a random funny preset message for the given category."""
        import random
        if category == "Valid Excuse":
            options = [
                "Shipment got flagged at the dock. Coast Guard sniffing everything.",
                "My driver skipped town with half the take. I am hunting him now.",
                "Register flooded when the pipe burst. Cash is ruined.",
                "Rival crew leaned on me last night. Took what I had.",
                "Supplier shorted me and vanished. I am bleeding too.",
            ]
        elif category == "Argue":
            options = [
                "You double the cut every month and act surprised when it breaks me.",
                "You want loyalty but you tax me like an enemy.",
                "Maybe if your protection actually worked I would still have money.",
                "You squeeze until nothing is left then ask why I am empty.",
                "You already own the block. What more do you want from me.",
            ]
        elif category == "Romance":
            options = [
                "If you break my legs can you at least hold my hand while you do it.",
                "This is the most toxic flirting I have ever been part of and I am weirdly invested.",
                "Are you here to collect money or emotionally ruin me because both seem likely.",
                "I cannot tell if I am scared of you or attracted to you and that feels medically concerning.",
                "If this is how you flirt I would hate to see how you propose.",
            ]
        else:
            return "..."
            
        return random.choice(options)

    def _get_boss_response(self, category: str, anger: float) -> str:
        """
        Boss replies: straight, blunt. If very angry, use harsher lines.
        Romance still gets short, cold shutdowns.
        """
        import random
        base = [
            "I did not ask for a story. I asked for money.",
            "Every excuse sounds the same when the envelope is empty.",
            "Talk slower. Pay faster.",
            "Your problems are not my concern. Your debt is.",
            "I gave you time. Time is over.",
        ]
        angry = [
            "You are done stalling. Pay or I start breaking inventory and bones.",
            "Next time I walk in, I am not asking.",
            "Keep talking and I will make an example out of your storefront.",
            "I promised mercy once. That promise expired.",
            "This ends tonight one way or the other.",
            "I'll be paying you a visit soon.",
        ]
        romance = [
            "This is business. Do not confuse it with anything else.",
            "You want affection. I want payment.",
            "I am not here to flirt. I am here to collect.",
            "Feelings do not change numbers.",
            "Save the charm. It does not lower your balance.",
        ]
        pool = base
        if anger >= 80.0:
            pool = angry
        if category.lower().startswith("romance"):
            pool = romance if anger < 80.0 else romance + angry
        return random.choice(pool)


