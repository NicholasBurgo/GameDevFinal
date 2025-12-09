"""Main renderer for game entities and map."""

import math
import random
from typing import Union

import cv2
import numpy as np
import pygame

from config import COLOR_BG, COLOR_DAY_OVER_BG, COLOR_DAY_OVER_TEXT, COLOR_TEXT, DAY_DURATION, TILE_SIZE
from entities import Cash, Customer, Litter, LitterCustomer, Player, ThiefCustomer
from map import TileMap


def format_game_time(day: int, timer: float, day_duration: float) -> str:
    """
    Convert game timer to time string (10AM to 5PM).
    
    Args:
        day: Current day number
        timer: Current timer value (0 to day_duration)
        day_duration: Total duration of a day in seconds
        
    Returns:
        Formatted time string like "Day 1 - 10 AM"
    """
    # Map timer (0 to day_duration) to hours (10 to 17, where 17 = 5PM)
    # 10AM to 5PM is 7 hours
    progress = min(1.0, max(0.0, timer / day_duration))
    hour_float = 10.0 + progress * 7.0  # 10AM to 5PM
    
    # Convert to hour (no minutes)
    hour = int(hour_float)
    
    # Format as 12-hour time with AM/PM
    if hour == 0:
        display_hour = 12
        period = "AM"
    elif hour < 12:
        display_hour = hour
        period = "AM"
    elif hour == 12:
        display_hour = 12
        period = "PM"
    else:
        display_hour = hour - 12
        period = "PM"
    
    return f"Day {day} - {display_hour} {period}"


class VideoPlayer:
    """Handles video playback using OpenCV."""
    
    def __init__(self, video_path: str) -> None:
        self.video_path = video_path
        self.cap = None
        self.fps = 30.0
        self.video_width = 0
        self.video_height = 0
        self.current_frame = None
        self.is_playing = False
        self.frame_time = 0.0
        self.total_frames = 0
        self.current_frame_index = 0
        
    def load(self) -> bool:
        """Load the video file. Returns True if successful."""
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                print(f"Warning: Could not open video file: {self.video_path}")
                return False
            
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.video_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.video_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            return True
        except Exception as e:
            print(f"Warning: Error loading video: {e}")
            return False
    
    def start(self) -> None:
        """Start playing the video from the beginning."""
        if self.cap is None:
            return
        # Reset video to first frame
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.is_playing = True
        self.current_frame_index = 0
        self.frame_time = 0.0
        # Read the first frame immediately
        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = frame_rgb
    
    def stop(self) -> None:
        """Stop playing the video."""
        self.is_playing = False
    
    def update(self, dt: float) -> bool:
        """
        Update video playback. Returns True if video is still playing, False if finished.
        
        Args:
            dt: Delta time in seconds
        """
        if not self.is_playing or self.cap is None:
            return False
        
        self.frame_time += dt
        frame_duration = 1.0 / self.fps
        
        # Read new frame if enough time has passed
        if self.frame_time >= frame_duration:
            ret, frame = self.cap.read()
            if not ret:
                # Video finished
                self.is_playing = False
                return False
            
            # Convert BGR to RGB for pygame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = frame_rgb
            
            self.frame_time -= frame_duration
            self.current_frame_index += 1
        
        return True
    
    def get_frame_surface(self, target_size: tuple[int, int]) -> pygame.Surface | None:
        """
        Get the current frame as a pygame Surface, scaled to target size.
        
        Args:
            target_size: (width, height) tuple for scaling
        """
        if self.current_frame is None:
            return None
        
        # Resize frame to target size
        resized = cv2.resize(self.current_frame, target_size)
        
        # Convert numpy array to pygame Surface using frombuffer (simpler and more reliable)
        frame_surface = pygame.image.frombuffer(resized.tobytes(), target_size, 'RGB')
        return frame_surface
    
    def release(self) -> None:
        """Release video resources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_playing = False


class Renderer:
    """Handles all drawing operations."""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.video_player: VideoPlayer | None = None
        self.venmo_bubble_rect: pygame.Rect | None = None  # Store Venmo bubble rect for click detection
        
        # Load phone hand background image
        self.phonehand_image: pygame.Surface | None = None
        try:
            phonehand_path = "assets/imgs/PhoneHand.png"
            loaded_image = pygame.image.load(phonehand_path)
            self.phonehand_image = loaded_image
        except (pygame.error, FileNotFoundError):
            print(f"Warning: Could not load phone hand image: {phonehand_path}")
            self.phonehand_image = None
        
        # Load boss fight battle scene image
        self.battle_scene_image: pygame.Surface | None = None
        try:
            battle_scene_path = "assets/imgs/Battlescene.png"
            loaded_image = pygame.image.load(battle_scene_path)
            self.battle_scene_image = loaded_image
        except (pygame.error, FileNotFoundError):
            print(f"Warning: Could not load battle scene image: {battle_scene_path}")
            self.battle_scene_image = None
        
        # Load floor texture
        self.floor_texture: pygame.Surface | None = None
        try:
            floor_path = "assets/imgs/Floor.png"
            loaded_image = pygame.image.load(floor_path).convert_alpha()
            # Scale to tile size
            self.floor_texture = pygame.transform.scale(loaded_image, (TILE_SIZE, TILE_SIZE))
        except Exception as e:
            print(f"Warning: Could not load floor texture: {e}")
            self.floor_texture = None

        # Load player portrait for boss fight (circular crop)
        self.player_boss_image: pygame.Surface | None = None
        try:
            player_boss_path = "assets/imgs/Playerbf.jpg"
            self.player_boss_image = self._load_circular_image(player_boss_path)
        except (pygame.error, FileNotFoundError) as e:
            print(f"Warning: Could not load player boss image: {e}")
            self.player_boss_image = None
        
        # Load boss portrait (tax boss) for top-right display
        self.tax_boss_image: pygame.Surface | None = None
        try:
            tax_boss_path = "assets/imgs/TaxBoss.jpg"
            self.tax_boss_image = pygame.image.load(tax_boss_path).convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            print(f"Warning: Could not load tax boss image: {e}")
            self.tax_boss_image = None
        
        # Load wall texture
        self.wall_texture: pygame.Surface | None = None
        try:
            wall_texture_path = "assets/imgs/Wall1.png"
            loaded_image = pygame.image.load(wall_texture_path)
            self.wall_texture = loaded_image
        except (pygame.error, FileNotFoundError):
            print(f"Warning: Could not load wall texture: {wall_texture_path}")
            self.wall_texture = None
        
        # Generate shelf texture
        self.shelf_texture = self._generate_shelf_texture()
        
        # Generate blue stone wall texture
        self.wall_stone_texture = self._generate_stone_wall_texture()
        
        # Generate door textures
        self.door_texture = self._generate_door_texture()
        self.office_door_texture = self._generate_office_door_texture()
        
        # Generate counter texture
        self.counter_texture = self._generate_counter_texture()
        
        # Falling cash for main menu background
        self.falling_cash: list[dict] = []  # List of {pos: Vector2, speed: float} dicts
        
        # Load computer images
        self.computer_images = []
        for i in range(1, 4):
            try:
                img = pygame.image.load(f"assets/imgs/Computer{i}.png").convert_alpha()
                img = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
                self.computer_images.append(img)
            except Exception as e:
                print(f"Warning: Could not load Computer{i}.png: {e}")
                self.computer_images.append(None)

        # Load optional weapon icons for mystery box
        self.mystery_item_icons: dict[str, pygame.Surface | None] = {}
        for key in ("nuke", "water_gun", "paper_plane"):
            path = f"assets/imgs/{key}.png"
            try:
                icon = pygame.image.load(path).convert_alpha()
                # Scale to a readable size for the table rows
                icon = pygame.transform.scale(icon, (72, 72))
                self.mystery_item_icons[key] = icon
            except Exception as e:
                print(f"Warning: Could not load {path}: {e}")
                self.mystery_item_icons[key] = None

        # Background screen image used when a computer UI is opened
        self.computer_screen_image: pygame.Surface | None = None
        try:
            self.computer_screen_image = pygame.image.load("assets/imgs/Screen.png").convert_alpha()
        except Exception as e:
            print(f"Warning: Could not load Screen.png: {e}")

        # Boss player portrait animation state
        self.player_boss_slide_active: bool = False
        self.player_boss_slide_start_ms: int | None = None
        self.player_boss_slide_duration: float = 0.6  # seconds
        self.player_boss_last_flash_active: bool = False
        self.player_boss_bob_phase: float = 0.0  # seconds accumulator for subtle bob
        # Tax boss portrait animation state
        self.tax_boss_slide_active: bool = False
        self.tax_boss_slide_start_ms: int | None = None
        self.tax_boss_slide_duration: float = 0.6  # seconds
        self.tax_boss_last_flash_active: bool = False
        self.tax_boss_bob_phase: float = 0.0

        # Store rects for tax man side buttons
        self.tax_side_buttons = {}

    def clear(self) -> None:
        """Clear the screen with background color."""
        self.screen.fill(COLOR_BG)

    def draw_map(self, tile_map: TileMap) -> None:
        """Draw the tile map."""
        tile_map.draw(self.screen, shelf_texture=self.shelf_texture, wall_stone_texture=self.wall_stone_texture,
                     counter_texture=self.counter_texture, computer_images=self.computer_images)
    
    def draw_room_with_camera(
        self,
        active_map: TileMap,
        camera_y_offset: float,
        player: "Player",
        customers: list = None,
        cash_items: list = None,
        litter_items: list = None,
        room_world_y_offset: float = 0.0,
    ) -> None:
        """
        Draw only the active room with camera offset.
        Camera moves to show the active room (office is stacked below store).
        
        Args:
            active_map: The currently active map (store or office)
            camera_y_offset: Camera Y offset (0 for store, positive for office)
            player: The player entity
            customers: Customers to draw
            cash_items: Cash items to draw
            litter_items: Litter items to draw
        """
        if customers is None:
            customers = []
        if cash_items is None:
            cash_items = []
        if litter_items is None:
            litter_items = []
        
        from config import TILE_SIZE, COLOR_BG
        
        # Fill entire screen with background color first (important for smaller rooms)
        self.screen.fill(COLOR_BG)
        
        # Draw map tiles with camera offset
        # room_world_y_offset is 0 for store, office_world_y_offset for office
        for row in range(active_map.rows):
            for col in range(active_map.cols):
                tile = active_map.map_data[row][col]
                
                x = col * TILE_SIZE
                # Convert local tile position to world position, then apply camera offset
                world_y = room_world_y_offset + (row * TILE_SIZE)
                y = world_y - int(camera_y_offset)  # Apply camera offset to get screen position
                
                # Only draw if visible on screen
                screen_height = self.screen.get_height()
                if y + TILE_SIZE >= 0 and y < screen_height:
                    rect = pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)
                    
                    from config import (
                        COLOR_COMPUTER, COLOR_COUNTER, COLOR_DOOR, COLOR_FLOOR, COLOR_NODE,
                        COLOR_OFFICE_DOOR, COLOR_SHELF, COLOR_WALL, TILE_ACTIVATION,
                        TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3,
                        TILE_COMPUTER, TILE_COUNTER, TILE_DOOR, TILE_FLOOR, TILE_NODE,
                        TILE_OFFICE_DOOR, TILE_SHELF, TILE_WALL
                    )
                    
                    if tile == TILE_FLOOR or tile == TILE_NODE:
                        if self.floor_texture is not None:
                            self.screen.blit(self.floor_texture, rect)
                        else:
                            color = COLOR_FLOOR
                            pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_WALL:
                        # Use blue stone texture if available, otherwise fall back to color
                        if self.wall_stone_texture is not None:
                            self.screen.blit(self.wall_stone_texture, rect)
                        else:
                            color = COLOR_WALL
                            pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_SHELF:
                        # Use shelf texture if available, otherwise fall back to color
                        if self.shelf_texture is not None:
                            self.screen.blit(self.shelf_texture, rect)
                        else:
                            color = COLOR_SHELF
                            pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_DOOR:
                        color = COLOR_DOOR
                        pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_OFFICE_DOOR:
                        color = COLOR_OFFICE_DOOR
                        pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_COUNTER:
                        # Use counter texture if available, otherwise fall back to color
                        if self.counter_texture is not None:
                            self.screen.blit(self.counter_texture, rect)
                        else:
                            color = COLOR_COUNTER
                            pygame.draw.rect(self.screen, color, rect)
                    elif tile == TILE_COMPUTER:
                        # Determine which computer to draw based on column
                        comp_idx = -1
                        if col == 1: comp_idx = 0
                        elif col == 5: comp_idx = 1
                        elif col == 9: comp_idx = 2
                        
                        if 0 <= comp_idx < len(self.computer_images) and self.computer_images[comp_idx]:
                            self.screen.blit(self.computer_images[comp_idx], rect)
                            # Slot-like light overlay (keeps PNG visible) with per-computer offset
                            self._draw_computer_light(rect, comp_idx)
                        else:
                            color = COLOR_COMPUTER
                            pygame.draw.rect(self.screen, color, rect)
                    elif tile in [TILE_ACTIVATION, TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3]:
                        # Activation tile uses floor texture/color
                        if self.floor_texture is not None:
                            self.screen.blit(self.floor_texture, rect)
                        else:
                            color = COLOR_FLOOR
                            pygame.draw.rect(self.screen, color, rect)
                    else:
                        if self.floor_texture is not None:
                            self.screen.blit(self.floor_texture, rect)
                        else:
                            color = COLOR_FLOOR
                            pygame.draw.rect(self.screen, color, rect)
        
        # Draw entities with camera offset
        for coin in cash_items:
            coin_screen_y = coin.pos.y - int(camera_y_offset)
            screen_height = self.screen.get_height()
            if -TILE_SIZE // 4 <= coin_screen_y < screen_height + TILE_SIZE // 4:
                from config import COLOR_CASH
                size = TILE_SIZE // 4
                coin_rect = pygame.Rect(
                    int(coin.pos.x - size / 2),
                    int(coin_screen_y - size / 2),
                    size,
                    size,
                )
                pygame.draw.rect(self.screen, COLOR_CASH, coin_rect)
        
        for litter in litter_items:
            litter_screen_y = litter.pos.y - int(camera_y_offset)
            screen_height = self.screen.get_height()
            if -TILE_SIZE // 4 <= litter_screen_y < screen_height + TILE_SIZE // 4:
                from config import COLOR_LITTER
                size = TILE_SIZE // 4
                pygame.draw.circle(self.screen, COLOR_LITTER,
                                 (int(litter.pos.x), int(litter_screen_y)), size)
        
        for customer in customers:
            customer_screen_y = customer.position.y - int(camera_y_offset)
            screen_height = self.screen.get_height()
            from config import CUSTOMER_RADIUS
            if -CUSTOMER_RADIUS <= customer_screen_y < screen_height + CUSTOMER_RADIUS:
                customer.draw(self.screen)
                # Draw health bar if customer has been hit
                if hasattr(customer, 'show_health_bar') and customer.show_health_bar:
                    self.draw_customer_health_bar(customer, pygame.Vector2(customer.position.x, customer_screen_y))
        
        # Draw player with camera offset
        player_screen_y = player.y - int(camera_y_offset)
        screen_height = self.screen.get_height()
        from config import PLAYER_RADIUS
        if -PLAYER_RADIUS <= player_screen_y < screen_height + PLAYER_RADIUS:
            from config import COLOR_PLAYER
            pygame.draw.circle(self.screen, COLOR_PLAYER,
                             (int(player.x), int(player_screen_y)), PLAYER_RADIUS)
    
    def draw_boss_approaching_circle(
        self,
        circle_position: pygame.Vector2,
        circle_radius: float,
        camera_y_offset: float = 0.0,
    ) -> None:
        """
        Draw the orange circle that approaches the player before boss fight.
        
        Args:
            circle_position: World position of the circle
            circle_radius: Radius of the circle
            camera_y_offset: Camera Y offset for screen positioning
        """
        # Convert world position to screen position
        screen_x = int(circle_position.x)
        screen_y = int(circle_position.y - camera_y_offset)
        
        # Orange color for the circle
        orange_color = (255, 140, 0)  # Same as COLOR_CUSTOMER
        
        # Draw the circle
        pygame.draw.circle(self.screen, orange_color, (screen_x, screen_y), int(circle_radius))
    
    def draw_tax_man_notification(self, tax_amount: int) -> None:
        """
        Draw a pixelated "Text message" notification on the left side.
        
        Args:
            tax_amount: Amount of tax to pay (not used in display, but kept for consistency)
        """
        from config import COLOR_TEXT
        
        # Draw pixelated "Text message" text on the left side
        # Create a small font and render at small size for pixelation
        # Use monospace font for better pixelated look
        # Base size is 30px, will be scaled 3x to 90px total (matching other pixelated text)
        small_font = pygame.font.SysFont("monospace", 30)
        text = "Text message"
        small_surface = small_font.render(text, True, COLOR_TEXT)
        
        # Scale up without smoothing for pixelated effect
        # Scale factor of 3 makes text 3x bigger (30px -> 90px)
        scale_factor = 3
        pixelated_surface = pygame.transform.scale(
            small_surface,
            (small_surface.get_width() * scale_factor, small_surface.get_height() * scale_factor)
        )
        
        # Position on left side, near top (matching vertical position of coins counter)
        text_rect = pixelated_surface.get_rect()
        text_rect.topleft = (20, 20)
        self.screen.blit(pixelated_surface, text_rect)

    def draw_entities(
        self,
        player: Player,
        customers: list[Union[Customer, ThiefCustomer, LitterCustomer]],
        cash_items: list[Cash],
        litter_items: list[Litter],
    ) -> None:
        """Draw all game entities."""
        # Draw dodge coins and litter first (on the floor)
        for coin in cash_items:
            coin.draw(self.screen)
        for litter in litter_items:
            litter.draw(self.screen)
        
        # Draw customers
        for customer in customers:
            customer.draw(self.screen)
            # Draw health bar if customer has been hit
            if hasattr(customer, 'show_health_bar') and customer.show_health_bar:
                self.draw_customer_health_bar(customer, customer.position)

        # Draw player last so it appears on top
        player.draw(self.screen)
    
    def draw_customer_health_bar(self, customer, position: pygame.Vector2) -> None:
        """
        Draw health bar above customer.
        
        Args:
            customer: Customer entity with health attributes
            position: Screen position to draw health bar at
        """
        if not hasattr(customer, 'health') or not hasattr(customer, 'max_health'):
            return
        
        health_ratio = customer.health / customer.max_health if customer.max_health > 0 else 0.0
        
        # Health bar dimensions
        bar_width = 40
        bar_height = 6
        bar_offset_y = customer.radius + 8  # Position above customer
        
        # Bar position
        bar_x = int(position.x - bar_width // 2)
        bar_y = int(position.y - bar_offset_y)
        
        # Draw background (black/dark)
        bg_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (0, 0, 0), bg_rect)
        
        # Draw health bar (green to red based on health)
        if health_ratio > 0:
            health_width = int(bar_width * health_ratio)
            health_rect = pygame.Rect(bar_x, bar_y, health_width, bar_height)
            
            # Color transitions from green (healthy) to red (low health)
            if health_ratio > 0.5:
                # Green to yellow
                r = int(255 * (1 - (health_ratio - 0.5) * 2))
                g = 255
                b = 0
            else:
                # Yellow to red
                r = 255
                g = int(255 * health_ratio * 2)
                b = 0
            
            pygame.draw.rect(self.screen, (r, g, b), health_rect)
        
        # Draw border
        pygame.draw.rect(self.screen, (255, 255, 255), bg_rect, 1)

    def load_day_over_video(self, video_path: str) -> bool:
        """
        Load the day over video. Returns True if successful.
        
        Args:
            video_path: Path to the video file
        """
        if self.video_player is not None:
            self.video_player.release()
        
        self.video_player = VideoPlayer(video_path)
        return self.video_player.load()
    
    def reset_day_over_video(self) -> None:
        """Reset the day over video to the beginning (for replay on new day)."""
        if self.video_player is not None:
            self.video_player.stop()
            # Video will restart when start() is called
    
    def draw_day_over_screen(self, day: int, video_playing: bool = False, dt: float = 0.016) -> bool:
        """
        Draw day over screen with video playback.
        
        Args:
            day: Current day number (unused, kept for compatibility)
            video_playing: Whether video is currently playing
            dt: Delta time for video update
        
        Returns:
            True if video is still playing, False if finished or not loaded
        """
        # Fill with black background
        self.screen.fill(COLOR_DAY_OVER_BG)
        
        # Try to play video if available
        if self.video_player is not None:
            if not self.video_player.is_playing and video_playing:
                self.video_player.start()
            
            if self.video_player.is_playing:
                # Update video
                still_playing = self.video_player.update(dt)
                
                if still_playing:
                    # Draw current frame - scale to fill entire screen
                    screen_size = (self.screen.get_width(), self.screen.get_height())
                    frame_surface = self.video_player.get_frame_surface(screen_size)
                    
                    if frame_surface is not None:
                        # Fill entire screen with video
                        self.screen.blit(frame_surface, (0, 0))
                    
                    return True
                else:
                    # Video finished
                    self.video_player.stop()
                    # Show instruction text after video
                    small_font = pygame.font.SysFont(None, 24)
                    instruction = "Press any key to continue"
                    instruction_surface = small_font.render(instruction, True, COLOR_DAY_OVER_TEXT)
                    instruction_rect = instruction_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 80))
                    self.screen.blit(instruction_surface, instruction_rect)
                    return False
        
        # Fallback: show text if video not available
        large_font = pygame.font.SysFont(None, 72)
        text = f"Day {day} - 5 PM"
        text_surface = large_font.render(text, True, COLOR_DAY_OVER_TEXT)
        text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
        self.screen.blit(text_surface, text_rect)
        
        small_font = pygame.font.SysFont(None, 24)
        instruction = "Press any key to continue"
        instruction_surface = small_font.render(instruction, True, COLOR_DAY_OVER_TEXT)
        instruction_rect = instruction_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 80))
        self.screen.blit(instruction_surface, instruction_rect)
        
        return False

    def _draw_iphone_frame(self, screen_width: int, screen_height: int) -> tuple[pygame.Rect, int, int]:
        """
        Draw iPhone frame/bezel and return the screen area bounds.
        
        Args:
            screen_width: Full screen width
            screen_height: Full screen height
            
        Returns:
            Tuple of (screen_rect, screen_x, screen_y) where screen_rect is the iPhone screen area
        """
        # Draw phone hand background image behind everything if available
        # EDIT PNG SIZE AND POSITION HERE:
        if self.phonehand_image is not None:
            # PNG SIZE: Change these values to adjust the image size
            # Currently set to 58% of screen width (slightly bigger than half)
            image_width = int(screen_width * 0.58)  # Slightly bigger than half width
            original_width, original_height = self.phonehand_image.get_size()
            aspect_ratio = original_height / original_width
            new_height = int(image_width * aspect_ratio * 1.15)  # 15% taller than aspect ratio
            scaled_image = pygame.transform.scale(self.phonehand_image, (image_width, new_height))
            
            # PNG POSITION: Change image_x and image_y to adjust position
            # Positioned slightly to the left (subtract 50 pixels from center)
            image_x = (screen_width - image_width) // 2 - 50  # Move 50px to the left
            image_y = (screen_height - new_height) // 2  # Vertical position (0 = top, higher = lower)
            self.screen.blit(scaled_image, (image_x, image_y))
        
        # iPhone proportions: approximately 9:19.5 aspect ratio (modern iPhone)
        # Calculate iPhone frame size (leave some margin around edges)
        bezel_width = min(screen_width, screen_height) * 0.08  # 8% bezel
        iphone_width = screen_width - bezel_width * 2
        iphone_height = iphone_width * (19.5 / 9)  # Maintain iPhone aspect ratio
        
        # If too tall, scale down based on height
        if iphone_height > screen_height - bezel_width * 2:
            iphone_height = screen_height - bezel_width * 2
            iphone_width = iphone_height * (9 / 19.5)
        
        # Increase the screen height by 30px
        iphone_height = iphone_height + 30
        
        # Center the iPhone screen (no bezel, just the screen area)
        # Move screen down and to the right slightly (split the difference)
        iphone_x = (screen_width - iphone_width) // 2 - 15  # Move 15px to the left (halfway back to center)
        iphone_y = (screen_height - iphone_height) // 2 + 60  # Move 60px down (more down)
        
        # Calculate screen area directly (no bezel)
        screen_padding = 0  # No padding since there's no bezel
        screen_x = iphone_x
        screen_y = iphone_y
        screen_w = iphone_width
        screen_h = iphone_height
        
        # Draw iPhone screen (white/light background)
        screen_rect = pygame.Rect(screen_x, screen_y, screen_w, screen_h)
        screen_bg_color = (221, 224, 233)  # Color #dde0e9 for phone screen
        pygame.draw.rect(self.screen, screen_bg_color, screen_rect, border_radius=20)
        
        return screen_rect, screen_x, screen_y

    def draw_tax_man_screen(
        self, 
        tax_amount: int, 
        menu_selection: int = 0,
        ai_response: str | None = None,
        awaiting_response: bool = False,
        input_mode: bool = False,
        player_argument: str = "",
        conversation: list[dict[str, str]] = None,
        boss_fight_triggered: bool = False,
        show_flash: bool = False,
        flash_timer: float = 0.0,
        flash_duration: float = 0.3,
        fade_alpha: int = 255,
        menu_locked: bool = False
    ) -> None:
        """
        Draw tax man screen with menu options inside an iPhone frame.
        
        Args:
            tax_amount: Amount of tax to pay
            menu_selection: Currently selected menu option (0 = Pay, 1 = Argue)
            ai_response: AI-generated response if player argued
            awaiting_response: Whether waiting for AI response
            input_mode: Whether player is typing their argument
            player_argument: The text the player has typed
            conversation: List of conversation messages [{"sender": "player"/"boss", "message": "..."}, ...]
            fade_alpha: Alpha value for fade out (255 = fully visible, 0 = invisible)
        """
        # If fading out, we need to draw everything to a temporary surface first
        original_screen = self.screen
        if fade_alpha < 255:
            # Create transparent surface
            screen_width, screen_height = original_screen.get_size()
            temp_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
            temp_surface.fill((0, 0, 0, 0)) # Clear transparent
            # Temporarily swap self.screen to target the temp surface
            self.screen = temp_surface
            
        if conversation is None:
            conversation = []
        # Reset Venmo bubble rect (will be set if we draw it)
        self.venmo_bubble_rect = None
        
        # Fill with black background
        self.screen.fill(COLOR_DAY_OVER_BG)
        
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        # Draw iPhone frame and get screen bounds
        screen_rect, screen_x, screen_y = self._draw_iphone_frame(screen_width, screen_height)
        screen_w = screen_rect.width
        screen_h = screen_rect.height
        
        # Create font for the tax man text (slightly smaller for iPhone screen)
        large_font = pygame.font.SysFont(None, 36)
        medium_font = pygame.font.SysFont(None, 28)
        small_font = pygame.font.SysFont(None, 20)
        input_font = pygame.font.SysFont(None, 24)  # Larger font for input box
        
        # Use dark text color for light iPhone background
        text_color = (30, 30, 30)
        
        # Title (positioned within iPhone screen)
        title_text = "Tax Dude"
        title_surface = large_font.render(title_text, True, text_color)
        title_rect = title_surface.get_rect(center=(screen_x + screen_w // 2, screen_y + 30))
        self.screen.blit(title_surface, title_rect)
        
        # Draw "You Owe" text in a message bubble (like a text message from Tax Dude)
        tax_text = f"You Owe: {tax_amount} dodge coins"
        max_tax_width = screen_w - 40
        tax_lines = self._wrap_text(tax_text, medium_font, max_tax_width - 20, text_color)
        
        # Calculate bubble size for tax amount
        bubble_padding = 15
        tax_bubble_height = len(tax_lines) * 32 + bubble_padding * 2
        if tax_lines:
            max_line_width = max([medium_font.size(line)[0] for line in tax_lines])
            tax_bubble_width = min(max_tax_width * 0.7, max(200, max_line_width + bubble_padding * 2))
        else:
            tax_bubble_width = 200
        
        # Position tax bubble to the left (like a received message)
        left_margin = 20
        tax_bubble_x = screen_x + left_margin
        tax_bubble_y = screen_y + 80
        
        # Draw name label "Tax Dude" above the bubble, left-aligned
        name_font = pygame.font.SysFont(None, 18)
        name_text = "Tax Dude"
        name_surface = name_font.render(name_text, True, (100, 100, 100))  # Gray color for name
        name_rect = name_surface.get_rect()
        name_rect.left = tax_bubble_x  # Left-align with bubble
        name_rect.bottom = tax_bubble_y - 5  # 5 pixels above bubble
        self.screen.blit(name_surface, name_rect)
        
        # Draw rounded message bubble (gray, like received message)
        tax_bubble_rect = pygame.Rect(tax_bubble_x, tax_bubble_y, tax_bubble_width, tax_bubble_height)
        bubble_color = (220, 220, 220)  # Light gray for received message
        pygame.draw.rect(self.screen, bubble_color, tax_bubble_rect, border_radius=15)
        
        # Draw text inside bubble (dark text on gray background, left-aligned within bubble)
        for i, line in enumerate(tax_lines):
            line_surface = medium_font.render(line, True, text_color)
            line_rect = line_surface.get_rect()
            line_rect.left = tax_bubble_x + bubble_padding  # Left-aligned
            line_rect.centery = tax_bubble_y + bubble_padding + i * 32 + 16
            self.screen.blit(line_surface, line_rect)
        
        # Draw Venmo message bubble below the "You Owe" message
        venmo_request_text = f"Requesting {tax_amount} dodge coins"
        venmo_url = "venmo.com/tax-dude/pay"
        
        # Combine text with URL (URL on new line)
        venmo_full_text = f"{venmo_request_text}\n{venmo_url}"
        venmo_lines = venmo_full_text.split('\n')
        
        # Calculate Venmo bubble size (need to account for wrapped text if URL is too long)
        venmo_max_width = max_tax_width - 20
        wrapped_venmo_lines = []
        for line in venmo_lines:
            wrapped = self._wrap_text(line, medium_font, venmo_max_width - bubble_padding * 2, text_color)
            wrapped_venmo_lines.extend(wrapped)
        
        venmo_bubble_height = len(wrapped_venmo_lines) * 32 + bubble_padding * 2
        if wrapped_venmo_lines:
            max_line_width = max([medium_font.size(line)[0] for line in wrapped_venmo_lines])
            venmo_bubble_width = min(max_tax_width * 0.7, max(200, max_line_width + bubble_padding * 2))
        else:
            venmo_bubble_width = 200
        
        # Position Venmo bubble below the tax bubble
        venmo_bubble_x = screen_x + left_margin
        venmo_bubble_y = tax_bubble_y + tax_bubble_height + 10  # 10 pixels spacing
        
        # Draw rounded message bubble for Venmo (gray, like received message)
        venmo_bubble_rect = pygame.Rect(venmo_bubble_x, venmo_bubble_y, venmo_bubble_width, venmo_bubble_height)
        self.venmo_bubble_rect = venmo_bubble_rect  # Store for click detection
        pygame.draw.rect(self.screen, bubble_color, venmo_bubble_rect, border_radius=15)
        
        # Draw text inside Venmo bubble
        for i, line in enumerate(wrapped_venmo_lines):
            # Make URL text slightly blue to look like a link
            if line == venmo_url or venmo_url in line:
                url_color = (0, 100, 255)  # Blue color for URL
            else:
                url_color = text_color
            line_surface = medium_font.render(line, True, url_color)
            line_rect = line_surface.get_rect()
            line_rect.left = venmo_bubble_x + bubble_padding  # Left-aligned
            line_rect.centery = venmo_bubble_y + bubble_padding + i * 32 + 16
            self.screen.blit(line_surface, line_rect)
        
        # Draw conversation history (chat messages)
        conversation_start_y = venmo_bubble_y + venmo_bubble_height + 20
        input_box_top = screen_y + screen_h - 70  # Position where input box starts
        max_conversation_height = input_box_top - conversation_start_y - 20  # Available space for messages
        
        # First pass: calculate total height of all messages
        total_height = 0
        message_heights = []
        max_msg_width = max_tax_width - 20
        max_bubble_width = int(max_msg_width * 0.7)
        available_text_width = max_bubble_width - bubble_padding * 2
        
        for msg in conversation:
            message = msg.get("message", "")
            msg_lines = self._wrap_text(message, medium_font, available_text_width, text_color)
            if msg_lines:
                max_line_width = max([medium_font.size(line)[0] for line in msg_lines])
                msg_bubble_width = min(max_bubble_width, max(200, max_line_width + bubble_padding * 2))
                actual_text_width = msg_bubble_width - bubble_padding * 2
                msg_lines = self._wrap_text(message, medium_font, actual_text_width, text_color)
            msg_bubble_height = len(msg_lines) * 32 + bubble_padding * 2
            message_heights.append(msg_bubble_height)
            total_height += msg_bubble_height + 10  # Include spacing between messages
        
        # Calculate scroll offset to keep newest messages visible at bottom
        scroll_offset = 0
        if total_height > max_conversation_height:
            # Scroll up so the bottom of the conversation aligns with the input box
            scroll_offset = total_height - max_conversation_height
        
        # Track if we've shown the "Tax Dude" name label yet (only show on first boss message)
        name_font = pygame.font.SysFont(None, 18)
        tax_dude_name_shown = False
        
        # Draw conversation messages with scroll offset
        current_y = conversation_start_y - scroll_offset
        for idx, msg in enumerate(conversation):
            sender = msg.get("sender", "boss")
            message = msg.get("message", "")
            
            # Determine max bubble width (70% of available width, matching initial bubbles)
            max_msg_width = max_tax_width - 20
            max_bubble_width = int(max_msg_width * 0.7)
            
            # Wrap text to fit within the bubble (accounting for padding)
            available_text_width = max_bubble_width - bubble_padding * 2
            msg_lines = self._wrap_text(message, medium_font, available_text_width, text_color)
            
            # Calculate actual bubble width based on wrapped text
            if msg_lines:
                max_line_width = max([medium_font.size(line)[0] for line in msg_lines])
                msg_bubble_width = min(max_bubble_width, max(200, max_line_width + bubble_padding * 2))
            else:
                msg_bubble_width = 200
            
            # Re-wrap if needed to ensure text fits (in case we had to adjust bubble width)
            if msg_lines:
                actual_text_width = msg_bubble_width - bubble_padding * 2
                msg_lines = self._wrap_text(message, medium_font, actual_text_width, text_color)
            
            # Calculate bubble height (matching initial bubble spacing: 32px per line)
            msg_bubble_height = message_heights[idx] if idx < len(message_heights) else len(msg_lines) * 32 + bubble_padding * 2
            
            # Position based on sender (player on right, boss on left)
            if sender == "player":
                msg_bubble_x = screen_x + screen_w - msg_bubble_width - left_margin
                msg_bubble_color = (0, 122, 255)  # Blue for sent messages
                msg_text_color = (255, 255, 255)  # White text
            else:  # boss
                msg_bubble_x = screen_x + left_margin
                msg_bubble_color = (220, 220, 220)  # Gray for received messages
                msg_text_color = text_color
                
                # Show "Tax Dude" name label only on first boss message
                if not tax_dude_name_shown:
                    name_text = "Tax Dude"
                    name_surface = name_font.render(name_text, True, (100, 100, 100))  # Gray color for name
                    name_rect = name_surface.get_rect()
                    name_rect.left = msg_bubble_x
                    name_rect.bottom = current_y - 5  # 5 pixels above bubble
                    visible_top = conversation_start_y
                    visible_bottom = input_box_top
                    if current_y + msg_bubble_height > visible_top and current_y < visible_bottom:
                        self.screen.blit(name_surface, name_rect)
                    tax_dude_name_shown = True
            
            # Only draw if within visible area (accounting for scroll)
            visible_top = conversation_start_y
            visible_bottom = input_box_top
            if current_y + msg_bubble_height > visible_top and current_y < visible_bottom:
                # Draw message bubble
                msg_bubble_rect = pygame.Rect(msg_bubble_x, current_y, msg_bubble_width, msg_bubble_height)
                pygame.draw.rect(self.screen, msg_bubble_color, msg_bubble_rect, border_radius=15)
                
                # Draw text inside bubble (matching initial bubble text positioning)
                for i, line in enumerate(msg_lines):
                    line_surface = medium_font.render(line, True, msg_text_color)
                    line_rect = line_surface.get_rect()
                    if sender == "player":
                        line_rect.right = msg_bubble_x + msg_bubble_width - bubble_padding
                    else:
                        line_rect.left = msg_bubble_x + bubble_padding
                    line_rect.centery = current_y + bubble_padding + i * 32 + 16
                    self.screen.blit(line_surface, line_rect)
            
            current_y += msg_bubble_height + 10  # Space between messages
        
        # Instructions at very bottom (typing removed)
        if boss_fight_triggered:
            instruction = "Press E to close"
        else:
            instruction = "Use arrows + Enter: Excuse / Argue / Romance / Pay. Press E to close."
        # When locked (paid or mad), force the simpler instruction
        if menu_locked:
            instruction = "Resolved. Press E to close."
        instruction_surface = pygame.font.SysFont(None, 16).render(instruction, True, (150, 150, 150))
        instruction_rect = instruction_surface.get_rect(center=(screen_x + screen_w // 2, screen_y + screen_h - 2))
        self.screen.blit(instruction_surface, instruction_rect)

        # Draw side buttons for quick actions
        # Move more to the right (+50) and bottom (+200 starts lower)
        self._draw_tax_side_buttons(screen_x + screen_w + 50, screen_y + 200, menu_selection, disabled=menu_locked)

        # Draw flash effect (white overlay)
        if show_flash and flash_timer < flash_duration:
            # Calculate flash intensity (starts at 255, fades to 0)
            progress = flash_timer / flash_duration
            # Use ease-out for smoother fade
            fade_progress = 1.0 - (1.0 - progress) * (1.0 - progress)
            
            # Inverse: 1.0 -> 0.0
            flash_alpha = int(255 * (1.0 - progress))
            
            if flash_alpha > 0:
                # Create a white surface with alpha for the flash
                screen_width, screen_height = self.screen.get_size()
                flash_surface = pygame.Surface((screen_width, screen_height))
                flash_surface.fill((255, 255, 255))
                flash_surface.set_alpha(flash_alpha)
                self.screen.blit(flash_surface, (0, 0))

                flash_surface.set_alpha(flash_alpha)
                self.screen.blit(flash_surface, (0, 0))

        if fade_alpha < 255:
            # Restore original screen first!
            self.screen = original_screen
            temp_surface.set_alpha(fade_alpha)
            self.screen.blit(temp_surface, (0, 0))
    
    def _draw_tax_side_buttons(self, start_x: int, start_y: int, selected_index: int = 0, disabled: bool = False) -> None:
        """Draw 4 menu options on the side of the phone."""
        buttons = [
            "Valid Excuse",
            "Argue",
            "Romance",
            "Pay"
        ]
        
        # Simple list layout
        button_height = 60
        spacing = 40
        
        # Pixelated text setup
        base_font_size = 24
        scale_factor = 2
        font = pygame.font.SysFont("monospace", base_font_size)
        
        self.tax_side_buttons = {}
        
        for i, label in enumerate(buttons):
            y = start_y + i * (button_height + spacing)
            
            # Use > for selected item
            if disabled:
                display_label = f"  {label}"
                color = (140, 140, 140)
            else:
                display_label = f"> {label}" if i == selected_index else f"  {label}"
                color = (255, 255, 0) if i == selected_index else (255, 255, 255)
            
            # Draw pixelated text
            text_surface = font.render(display_label, True, color)
            # Scale up
            scaled_surface = pygame.transform.scale(
                text_surface, 
                (text_surface.get_width() * scale_factor, text_surface.get_height() * scale_factor)
            )
            
            # Position
            rect = scaled_surface.get_rect(topleft=(start_x, y))
            self.screen.blit(scaled_surface, rect)
            
            # Store rect for mouse click support (optional but good to keep)
            # Remove the "> " part for the mapping key logic, but keep rect coverage
            # Actually, standard hit rect might need to be wider?
            # Let's clean up label for dict key logic if I want to keep click support
            # Original code used label name as key.
            self.tax_side_buttons[label] = rect

    def is_venmo_bubble_clicked(self, mouse_pos: tuple[int, int]) -> bool:
        """
        Check if the mouse position is within the Venmo bubble.
        
        Args:
            mouse_pos: (x, y) tuple of mouse position
            
        Returns:
            True if clicked on Venmo bubble, False otherwise
        """
        if self.venmo_bubble_rect is None:
            return False
        return self.venmo_bubble_rect.collidepoint(mouse_pos)

    def get_tax_side_button_clicked(self, mouse_pos: tuple[int, int]) -> str | None:
        """
        Check which side button was clicked.
        
        Returns:
            Label of the clicked button or None
        """
        for label, rect in self.tax_side_buttons.items():
            if rect.collidepoint(mouse_pos):
                return label
        return None
    
    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int, text_color: tuple[int, int, int] = COLOR_DAY_OVER_TEXT) -> list[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            test_surface = font.render(test_line, True, text_color)
            if test_surface.get_width() <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

    def draw_time_counter(self, day: int, timer: float) -> None:
        """
        Draw pixelated day and time counter at the top center of the screen.
        
        Args:
            day: Current day number
            timer: Current timer value
        """
        # Get formatted time string
        time_str = format_game_time(day, timer, DAY_DURATION)
        
        # Create a small font and render at small size for pixelation
        # Use monospace font for better pixelated look
        # Base size is 30px, will be scaled 3x to 90px total
        small_font = pygame.font.SysFont("monospace", 30)
        small_surface = small_font.render(time_str, True, COLOR_TEXT)
        
        # Scale up without smoothing for pixelated effect
        # Scale factor of 3 makes text 3x bigger (30px -> 90px)
        scale_factor = 3
        pixelated_surface = pygame.transform.scale(
            small_surface,
            (small_surface.get_width() * scale_factor, small_surface.get_height() * scale_factor)
        )
        
        # Center at top of screen
        text_rect = pixelated_surface.get_rect(center=(self.screen.get_width() // 2, 60))
        self.screen.blit(pixelated_surface, text_rect)

    def draw_coins_counter(self, coins: int) -> None:
        """
        Draw pixelated dodge coins counter at the top right of the screen.
        
        Args:
            coins: Current number of collected dodge coins
        """
        # Format coins string - just the number
        coins_str = str(coins)
        
        # Create a small font and render at small size for pixelation
        # Use monospace font for better pixelated look
        # Base size is 30px, will be scaled 3x to 90px total
        small_font = pygame.font.SysFont("monospace", 30)
        small_surface = small_font.render(coins_str, True, COLOR_TEXT)
        
        # Scale up without smoothing for pixelated effect
        # Scale factor of 3 makes text 3x bigger (30px -> 90px)
        scale_factor = 3
        pixelated_surface = pygame.transform.scale(
            small_surface,
            (small_surface.get_width() * scale_factor, small_surface.get_height() * scale_factor)
        )
        
        # Position at top right of screen, same vertical level as time counter (y=50)
        text_rect = pixelated_surface.get_rect()
        text_rect.topright = (self.screen.get_width() - 30, 10)
        self.screen.blit(pixelated_surface, text_rect)

    def draw_mystery_box_screen(
        self,
        coins: int,
        items: list[dict],
        owned: dict[str, bool],
        message: str,
        last_item: dict | None = None,
        nuke_triggered: bool = False,
        computer_image: pygame.Surface | None = None,
    ) -> None:
        """Render the Computer 2 mystery box UI."""
        # Prefer shared computer screen background if available
        if computer_image is None and self.computer_screen_image is not None:
            computer_image = self.computer_screen_image

        # Nuke result: full white game over screen
        if nuke_triggered:
            self.screen.fill((255, 255, 255))
            title_font = pygame.font.SysFont("monospace", 72, bold=True)
            body_font = pygame.font.SysFont("monospace", 32)
            title_surface = title_font.render("GAME OVER", True, (10, 10, 10))
            title_rect = title_surface.get_rect(center=(self.screen.get_width() // 2, 240))
            self.screen.blit(title_surface, title_rect)

            subtitle = "Nuke detonated from the mystery box."
            subtitle_surface = body_font.render(subtitle, True, (30, 30, 30))
            subtitle_rect = subtitle_surface.get_rect(center=(self.screen.get_width() // 2, 320))
            self.screen.blit(subtitle_surface, subtitle_rect)

            prompt_surface = body_font.render("Press Enter/Esc/E to leave.", True, (40, 40, 40))
            prompt_rect = prompt_surface.get_rect(center=(self.screen.get_width() // 2, 400))
            self.screen.blit(prompt_surface, prompt_rect)
            return

        self.screen.fill(COLOR_BG)

        # Draw computer image as background if available
        if computer_image:
            s_w, s_h = self.screen.get_size()
            img_w, img_h = computer_image.get_size()
            scale = min(s_w / img_w, s_h / img_h) * 0.8
            new_size = (int(img_w * scale), int(img_h * scale))
            scaled_img = pygame.transform.scale(computer_image, new_size)
            rect = scaled_img.get_rect(center=(s_w // 2, s_h // 2))
            self.screen.blit(scaled_img, rect)

        title_font = pygame.font.SysFont("monospace", 56, bold=True)
        body_font = pygame.font.SysFont("monospace", 28)
        reel_font = pygame.font.SysFont("monospace", 72, bold=True)
        small_font = pygame.font.SysFont("monospace", 22)

        # Title aligned similar to Computer 1 layout
        title_surface = title_font.render("Mystery Box", True, (0, 0, 0))
        title_rect = title_surface.get_rect(center=(self.screen.get_width() // 2, 200))
        self.screen.blit(title_surface, title_rect)

        # Reel-style symbols line (use simple symbols instead of names; highlight last pull)
        # Card-style symbols
        symbol_map = [
            ("nuke", "♠"),         # spade
            ("water_gun", "♥"),    # heart
            ("paper_plane", "♦"),  # diamond
            ("nothing", "♣"),      # club
        ]
        reels_items = []
        last_key = last_item.get("key", "") if last_item else ""
        for key, sym in symbol_map:
            if key == last_key:
                reels_items.append(f"[{sym}]")
            else:
                reels_items.append(sym)
        reel_text = " | ".join(reels_items)
        reel_surface = reel_font.render(reel_text, True, (0, 0, 0))
        reel_rect = reel_surface.get_rect(center=(self.screen.get_width() // 2, 416))
        self.screen.blit(reel_surface, reel_rect)

        # Coins and pricing (placed where coins/bet would be)
        coins_surface = body_font.render(f"Coins: {coins}", True, (0, 0, 0))
        coins_rect = coins_surface.get_rect(center=(self.screen.get_width() // 2, 496))
        self.screen.blit(coins_surface, coins_rect)

        cost_surface = body_font.render("Roll: 5 coins (Enter)   |   Nuke: 100 coins (N)", True, (0, 0, 0))
        cost_rect = cost_surface.get_rect(center=(self.screen.get_width() // 2, 536))
        self.screen.blit(cost_surface, cost_rect)

        # Inventory summary
        inv_strings = []
        for key, label in [("nuke", "Nuke"), ("water_gun", "Water Gun"), ("paper_plane", "Paper Plane")]:
            owned_flag = owned.get(key, False)
            inv_strings.append(f"[{'X' if owned_flag else ' '}] {label}")
        inv_text = "Owned: " + " | ".join(inv_strings)
        inv_surface = body_font.render(inv_text, True, (0, 0, 0))
        inv_rect = inv_surface.get_rect(center=(self.screen.get_width() // 2, 576))
        self.screen.blit(inv_surface, inv_rect)

        # Message line
        message_surface = body_font.render(message, True, (0, 0, 0))
        message_rect = message_surface.get_rect(center=(self.screen.get_width() // 2, 616))
        self.screen.blit(message_surface, message_rect)

        # Instructions (aligned near bottom like slot machine)
        instructions = [
            "Enter: Roll (5 coins)",
            "N: Buy guaranteed Nuke (100 coins)",
            "E or Esc: Leave computer",
        ]
        inst_y = 696
        for line in instructions:
            line_surface = small_font.render(line, True, (0, 0, 0))
            line_rect = line_surface.get_rect(center=(self.screen.get_width() // 2, inst_y))
            self.screen.blit(line_surface, line_rect)
            inst_y += 26

    def draw_slot_machine_screen(self, coins: int, bet: int, reels: list[str], message: str, computer_image: pygame.Surface | None = None) -> None:
        """Render a simple slot machine UI."""
        # Prefer shared computer screen background if available
        if computer_image is None and self.computer_screen_image is not None:
            computer_image = self.computer_screen_image

        self.screen.fill(COLOR_BG)

        # Draw computer image as background if available
        if computer_image:
            # Scale to verify it's visible (fit screen mostly)
            s_w, s_h = self.screen.get_size()
            img_w, img_h = computer_image.get_size()
            
            # Use nearest neighbor scaling for pixel art
            scale = min(s_w / img_w, s_h / img_h) * 0.8  # 80% screen size
            new_size = (int(img_w * scale), int(img_h * scale))
            
            scaled_img = pygame.transform.scale(computer_image, new_size)
            rect = scaled_img.get_rect(center=(s_w // 2, s_h // 2))
            self.screen.blit(scaled_img, rect)


        title_font = pygame.font.SysFont("monospace", 56, bold=True)
        body_font = pygame.font.SysFont("monospace", 32)
        reel_font = pygame.font.SysFont("monospace", 72, bold=True)

        # Title
        title_surface = title_font.render("Galaxy Slots", True, (0, 0, 0))
        title_rect = title_surface.get_rect(center=(self.screen.get_width() // 2, 200))
        self.screen.blit(title_surface, title_rect)

        # Reels
        reel_text = " | ".join(reels) if reels else "X | O | X"
        reel_surface = reel_font.render(reel_text, True, (0, 0, 0))
        reel_rect = reel_surface.get_rect(center=(self.screen.get_width() // 2, 416))
        self.screen.blit(reel_surface, reel_rect)

        # Balance and bet input
        coins_surface = body_font.render(f"Coins: {coins}", True, (0, 0, 0))
        coins_rect = coins_surface.get_rect(center=(self.screen.get_width() // 2, 496))
        self.screen.blit(coins_surface, coins_rect)

        bet_surface = body_font.render(f"Bet: {bet}", True, (0, 0, 0))
        bet_rect = bet_surface.get_rect(center=(self.screen.get_width() // 2, 536))
        self.screen.blit(bet_surface, bet_rect)

        # Message line
        message_surface = body_font.render(message, True, (0, 0, 0))
        message_rect = message_surface.get_rect(center=(self.screen.get_width() // 2, 616))
        self.screen.blit(message_surface, message_rect)

        # Instructions
        instructions = [
            "Press W or Up to increase bet.",
            "Press S or Down to decrease bet.",
            "Press Enter to spin.",
            "Press E or Esc to leave."
        ]
        y = 696
        for line in instructions:
            line_surface = body_font.render(line, True, (0, 0, 0))
            line_rect = line_surface.get_rect(center=(self.screen.get_width() // 2, y))
            self.screen.blit(line_surface, line_rect)
            y += 38

    def draw_rain_bet_screen(self, computer_image: pygame.Surface | None = None) -> None:
        """Render Computer 3 Rain Bet placeholder."""
        if computer_image is None and self.computer_screen_image is not None:
            computer_image = self.computer_screen_image

        self.screen.fill(COLOR_BG)

        if computer_image:
            s_w, s_h = self.screen.get_size()
            img_w, img_h = computer_image.get_size()
            scale = min(s_w / img_w, s_h / img_h) * 0.8
            new_size = (int(img_w * scale), int(img_h * scale))
            scaled_img = pygame.transform.scale(computer_image, new_size)
            rect = scaled_img.get_rect(center=(s_w // 2, s_h // 2))
            self.screen.blit(scaled_img, rect)

        title_font = pygame.font.SysFont("monospace", 56, bold=True)
        reel_font = pygame.font.SysFont("monospace", 72, bold=True)

        title_surface = title_font.render("Rain Bet", True, (0, 0, 0))
        title_rect = title_surface.get_rect(center=(self.screen.get_width() // 2, 200))
        self.screen.blit(title_surface, title_rect)

        # Place text where slot reels normally sit
        reel_surface = reel_font.render("Unavailable", True, (0, 0, 0))
        reel_rect = reel_surface.get_rect(center=(self.screen.get_width() // 2, 416))
        self.screen.blit(reel_surface, reel_rect)
    
    def draw_boss_fight_screen(self, show_flash: bool = False, flash_timer: float = 0.0, flash_duration: float = 0.3, 
                               boss_health: float = 100.0, player_health: float = 100.0, menu_selection: int = 0,
                               fight_options: list[dict] | None = None, fight_prompt: str = "",
                               boss_hurt_timer: float = 0.0, player_hurt_timer: float = 0.0, hurt_flash_duration: float = 0.3) -> None:
        """
        Draw boss fight screen using BattleScene.png image with Pokemon-style flash effect.
        
        Args:
            show_flash: Whether to show flash effect (before battle scene)
            flash_timer: Current flash timer value
            flash_duration: Total flash duration in seconds
            boss_health: Tax boss health (0.0 to 1.0)
            player_health: Player health (0.0 to 1.0)
        """
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        # ===== HEALTH BAR POSITIONS (EASY TO ADJUST) =====
        # Boss health bar (top-left area)
        BOSS_BAR_X = 600
        BOSS_BAR_Y = 300
        BOSS_BAR_WIDTH = 400
        BOSS_BAR_HEIGHT = 30
        
        # Player health bar (bottom-right area)
        PLAYER_BAR_X = 1720  
        PLAYER_BAR_Y = 817  
        PLAYER_BAR_WIDTH = 400
        PLAYER_BAR_HEIGHT = 30
        # =================================================
        
        # Fill with blue-ish background
        self.screen.fill((100, 150, 200))  # Light blue background
        
        # Draw battle scene first (will be visible after flash)
        battle_scene_drawn = False
        if self.battle_scene_image is not None:
            # Scale image to fit screen while maintaining aspect ratio (show whole image)
            img_width, img_height = self.battle_scene_image.get_size()
            scale_x = screen_width / img_width
            scale_y = screen_height / img_height
            scale = min(scale_x, scale_y)  # Scale to fit entire image on screen
            
            scaled_width = int(img_width * scale)
            scaled_height = int(img_height * scale)
            scaled_image = pygame.transform.scale(self.battle_scene_image, (scaled_width, scaled_height))
            
            # Center the image on screen
            x = (screen_width - scaled_width) // 2
            y = (screen_height - scaled_height) // 2
            self.screen.blit(scaled_image, (x, y))
            battle_scene_drawn = True
        
        # Draw player portrait near player health area (slide in after flash)
        if self.player_boss_image is not None:
            # Track flash state to start slide after transition
            if show_flash and flash_timer < flash_duration:
                self.player_boss_last_flash_active = True
                self.player_boss_slide_active = False
                self.player_boss_slide_start_ms = None
                # Do not draw during flash
                pass
            elif self.player_boss_last_flash_active:
                self.player_boss_slide_active = True
                self.player_boss_slide_start_ms = pygame.time.get_ticks()
                self.player_boss_last_flash_active = False
            
            # Skip drawing if flash is still running
            if show_flash and flash_timer < flash_duration:
                pass
            else:

                img_w, img_h = self.player_boss_image.get_size()
                # Larger footprint (allow upscale if source is small)
                max_w = int(screen_width * 0.30)
                max_h = int(screen_height * 0.45)
                scale = min(max_w / img_w, max_h / img_h)
                # Soft cap to avoid extreme blow-up
                scale = min(scale, 2.0)
                new_size = (int(img_w * scale), int(img_h * scale))
                scaled_img = pygame.transform.scale(self.player_boss_image, new_size)
                # Position above the bottom margin, to the left of the player health bar
                margin_x = 380
                margin_y = 140
                pos_x = margin_x
                if self.player_boss_slide_active and self.player_boss_slide_start_ms is not None:
                    elapsed = (pygame.time.get_ticks() - self.player_boss_slide_start_ms) / 1000.0
                    duration = max(0.05, self.player_boss_slide_duration)
                    t = max(0.0, min(1.0, elapsed / duration))
                    # Start fully off-screen to the left
                    start_x = int(-new_size[0] * 1.1)
                    # Ease-out quad
                    eased = 1 - (1 - t) * (1 - t)
                    pos_x = start_x + (margin_x - start_x) * eased
                    if t >= 1.0:
                        self.player_boss_slide_active = False
                # Quicker, more noticeable vertical bob (~2s cycle, slightly larger)
                self.player_boss_bob_phase = (self.player_boss_bob_phase + (1 / 60.0)) % 2.0
                bob_offset = math.sin((self.player_boss_bob_phase / 2.0) * 2 * math.pi) * 6
                # Hurt shake
                shake_x = 0
                shake_y = 0
                if player_hurt_timer > 0 and hurt_flash_duration > 0:
                    amp = 6 * max(0.0, min(1.0, player_hurt_timer / hurt_flash_duration))
                    shake_x = random.uniform(-amp, amp)
                    shake_y = random.uniform(-amp, amp)
                pos_y = screen_height - new_size[1] - margin_y + bob_offset + shake_y
                pos_x += shake_x
                self.screen.blit(scaled_img, (pos_x, pos_y))
        
        # Draw tax boss portrait at top right (slide in after flash, with bob)
        if self.tax_boss_image is not None:
            # Track flash state for slide trigger
            if show_flash and flash_timer < flash_duration:
                self.tax_boss_last_flash_active = True
                self.tax_boss_slide_active = False
                self.tax_boss_slide_start_ms = None
            elif self.tax_boss_last_flash_active:
                self.tax_boss_slide_active = True
                self.tax_boss_slide_start_ms = pygame.time.get_ticks()
                self.tax_boss_last_flash_active = False

            # Skip drawing during flash
            if not (show_flash and flash_timer < flash_duration):
                img_w, img_h = self.tax_boss_image.get_size()
                max_w = int(screen_width * 0.20)
                max_h = int(screen_height * 0.25)
                scale = min(max_w / img_w, max_h / img_h)
                scale = min(scale, 2.0)
                new_size = (int(img_w * scale), int(img_h * scale))
                scaled_img = pygame.transform.scale(self.tax_boss_image, new_size)
                # Target position (inset left/down)
                margin_x = 470
                margin_y = 230
                pos_x = screen_width - new_size[0] - margin_x
                pos_y_base = margin_y
                # Slide from right edge
                if self.tax_boss_slide_active and self.tax_boss_slide_start_ms is not None:
                    elapsed = (pygame.time.get_ticks() - self.tax_boss_slide_start_ms) / 1000.0
                    duration = max(0.05, self.tax_boss_slide_duration)
                    t = max(0.0, min(1.0, elapsed / duration))
                    start_x = screen_width + int(new_size[0] * 1.1)
                    eased = 1 - (1 - t) * (1 - t)
                    pos_x = start_x + (pos_x - start_x) * eased
                    if t >= 1.0:
                        self.tax_boss_slide_active = False
                # Bobbing (match player cadence)
                self.tax_boss_bob_phase = (self.tax_boss_bob_phase + (1 / 60.0)) % 2.0
                bob_offset = math.sin((self.tax_boss_bob_phase / 2.0) * 2 * math.pi) * 6
                # Hurt shake
                shake_x = 0
                shake_y = 0
                if boss_hurt_timer > 0 and hurt_flash_duration > 0:
                    amp = 6 * max(0.0, min(1.0, boss_hurt_timer / hurt_flash_duration))
                    shake_x = random.uniform(-amp, amp)
                    shake_y = random.uniform(-amp, amp)
                pos_y = pos_y_base + bob_offset + shake_y
                pos_x += shake_x
                self.screen.blit(scaled_img, (pos_x, pos_y))

        # Boss intro transition: black -> expanding white circle -> white closing to center
        if show_flash and flash_timer < flash_duration:
            progress = max(0.0, min(1.0, flash_timer / max(flash_duration, 1e-6)))
            stage1_end = 0.2  # Black screen hold
            stage2_end = 0.6  # Expanding circle completes, white screen reached
            
            if progress < stage1_end:
                # Full black screen
                self.screen.fill((0, 0, 0))
            elif progress < stage2_end:
                # Black background with an expanding white circle from the center
                self.screen.fill((0, 0, 0))
                circle_progress = (progress - stage1_end) / (stage2_end - stage1_end)
                circle_progress = max(0.0, min(1.0, circle_progress))
                max_radius = int(math.hypot(screen_width, screen_height) * 0.6)
                radius = int(max_radius * circle_progress)
                if radius > 0:
                    pygame.draw.circle(
                        self.screen,
                        (255, 255, 255),
                        (screen_width // 2, screen_height // 2),
                        radius
                    )
            else:
                # White screen that closes from top and bottom toward the center
                band_progress = (progress - stage2_end) / max(1e-6, (1.0 - stage2_end))
                band_progress = max(0.0, min(1.0, band_progress))
                cover_height = int((screen_height / 2) * (1.0 - band_progress))
                if cover_height > 0:
                    # Draw white bands from the top and bottom inward
                    pygame.draw.rect(self.screen, (255, 255, 255), (0, 0, screen_width, cover_height))
                    pygame.draw.rect(
                        self.screen,
                        (255, 255, 255),
                        (0, screen_height - cover_height, screen_width, cover_height)
                    )
        
        # Fallback if image not loaded
        if not battle_scene_drawn:
            self.screen.fill((0, 0, 0))
            large_font = pygame.font.SysFont(None, 72)
            text = "BOSS FIGHT INITIATED"
            text_surface = large_font.render(text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(screen_width // 2, screen_height // 2))
            self.screen.blit(text_surface, text_rect)
        
        # Hurt flashes (boss: yellow, player: red)
        if boss_hurt_timer > 0 and hurt_flash_duration > 0:
            alpha = int(180 * (boss_hurt_timer / hurt_flash_duration))
            alpha = max(0, min(255, alpha))
            if alpha > 0:
                overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
                overlay.fill((255, 230, 120, alpha))
                self.screen.blit(overlay, (0, 0))
        if player_hurt_timer > 0 and hurt_flash_duration > 0:
            alpha = int(180 * (player_hurt_timer / hurt_flash_duration))
            alpha = max(0, min(255, alpha))
            if alpha > 0:
                overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
                overlay.fill((255, 80, 80, alpha))
                self.screen.blit(overlay, (0, 0))
        
        # Draw health bars (only if not flashing, or after flash)
        if not show_flash or flash_timer >= flash_duration:
            # Boss health bar (top-left)
            boss_bar_color = self._get_health_bar_color(boss_health)
            self._draw_health_bar(
                BOSS_BAR_X, BOSS_BAR_Y, BOSS_BAR_WIDTH, BOSS_BAR_HEIGHT,
                boss_health / 100.0, bar_color=boss_bar_color, bg_color=(100, 30, 30)
            )
            
            # Player health bar (bottom-right) - shrinks from right side
            player_bar_color = self._get_health_bar_color(player_health)
            self._draw_health_bar(
                PLAYER_BAR_X, PLAYER_BAR_Y, PLAYER_BAR_WIDTH, PLAYER_BAR_HEIGHT,
                player_health / 100.0, bar_color=player_bar_color, bg_color=(100, 30, 30),
                align_right=True  # Player bar shrinks from right
            )
            
            # ===== MENU BUTTON POSITIONS (EASY TO ADJUST) =====
            MENU_BUTTONS_X = 1600 # 400 pixels from right edge (moved left)
            MENU_BUTTONS_Y = 1100 # 400 pixels from bottom (moved up)
            BUTTON_SPACING = 80  # Space between buttons (closer together)
            # =================================================
            # Draw menu buttons only if provided (hide when not player's turn)
            if fight_options:
                self._draw_boss_fight_menu(MENU_BUTTONS_X, MENU_BUTTONS_Y, BUTTON_SPACING, menu_selection, fight_options or [])
            
            # Draw prompt near menu (pixelated text only, no box)
            if fight_prompt:
                prompt_font = pygame.font.SysFont("monospace", 40, bold=True)
                lines = fight_prompt.split("\n")
                for i, line in enumerate(lines):
                    prompt_surface = prompt_font.render(line, True, (255, 255, 255))
                    self.screen.blit(prompt_surface, (MENU_BUTTONS_X - 1330, MENU_BUTTONS_Y + 10 + i * 46))
    
    def _get_health_bar_color(self, health: float) -> tuple:
        """
        Get health bar color based on health value.
        Green at 100%, Yellow at 50%, Red at 25%, with smooth transitions.
        
        Args:
            health: Health value (0-100)
            
        Returns:
            RGB color tuple
        """
        health = max(0.0, min(100.0, health))
        
        if health >= 50.0:
            # Interpolate between green (100%) and yellow (50%)
            # health 100 = 1.0, health 50 = 0.0
            t = (health - 50.0) / 50.0  # 0.0 to 1.0
            # Green: (50, 200, 50), Yellow: (255, 255, 50)
            r = int(50 + (255 - 50) * (1.0 - t))
            g = int(200 + (255 - 200) * (1.0 - t))
            b = int(50 + (50 - 50) * (1.0 - t))
            return (r, g, b)
        else:
            # Interpolate between yellow (50%) and red (25%)
            # health 50 = 1.0, health 25 = 0.0, health < 25 = red
            if health >= 25.0:
                t = (health - 25.0) / 25.0  # 0.0 to 1.0
                # Yellow: (255, 255, 50), Red: (220, 50, 50)
                r = int(220 + (255 - 220) * t)
                g = int(50 + (255 - 50) * t)
                b = int(50 + (50 - 50) * t)
                return (r, g, b)
            else:
                # Below 25% - solid red
                return (220, 50, 50)
    
    def _draw_health_bar(self, x: int, y: int, width: int, height: int, 
                         health: float, bar_color: tuple, bg_color: tuple, align_right: bool = False) -> None:
        """
        Draw a health bar without text.
        
        Args:
            x: X position (left)
            y: Y position (top)
            width: Bar width
            height: Bar height
            health: Health value (0.0 to 1.0)
            bar_color: Color of the filled health bar (RGB tuple)
            bg_color: Color of the background/empty part (RGB tuple)
            align_right: If True, bar shrinks from right (filled portion on right). If False, shrinks from left.
        """
        # Clamp health to valid range
        health = max(0.0, min(1.0, health))
        
        # Draw background (empty bar)
        bg_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, bg_color, bg_rect)
        
        # Draw border
        pygame.draw.rect(self.screen, (0, 0, 0), bg_rect, width=2)
        
        # Draw filled health portion
        if health > 0:
            filled_width = int(width * health)
            if align_right:
                # Bar shrinks from right - filled portion starts from right side
                health_x = x + (width - filled_width)
            else:
                # Bar shrinks from left - filled portion starts from left side
                health_x = x
            health_rect = pygame.Rect(health_x, y, filled_width, height)
            pygame.draw.rect(self.screen, bar_color, health_rect)

    def _load_circular_image(self, path: str) -> pygame.Surface | None:
        """
        Load an image and crop it to a circle with transparent background.
        Returns a surface with per-pixel alpha or None on failure.
        """
        try:
            img = pygame.image.load(path).convert_alpha()
        except Exception as e:
            print(f"Warning: Could not load image {path}: {e}")
            return None
        
        w, h = img.get_size()
        size = min(w, h)
        
        # Create square surface and center-crop
        square_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        offset_x = (w - size) // 2
        offset_y = (h - size) // 2
        square_surface.blit(img, (-offset_x, -offset_y))
        
        # Create circular mask
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        # Slightly smaller radius for a tighter crop
        radius = int((size // 2) * 0.78)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), radius)
        # Cut off bottom half
        pygame.draw.rect(mask, (0, 0, 0, 0), (0, size // 2, size, size // 2))
        
        # Apply mask (multiply alpha)
        square_surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return square_surface
    
    def _generate_shelf_texture(self) -> pygame.Surface:
        """
        Generate a shelf texture that looks like a wooden store shelf with products.
        
        Returns:
            A pygame Surface with the shelf texture
        """
        from config import TILE_SIZE, COLOR_SHELF
        
        # Create surface for shelf texture
        texture = pygame.Surface((TILE_SIZE, TILE_SIZE))
        
        # Base shelf color (brown/wooden)
        base_color = COLOR_SHELF  # (140, 120, 80)
        texture.fill(base_color)
        
        # Draw shelf structure - horizontal shelves
        shelf_color = (100, 80, 50)  # Darker brown for shelf edges
        shelf_thickness = max(2, TILE_SIZE // 20)
        
        # Top shelf edge
        pygame.draw.rect(texture, shelf_color, (0, 0, TILE_SIZE, shelf_thickness))
        # Bottom shelf edge
        pygame.draw.rect(texture, shelf_color, (0, TILE_SIZE - shelf_thickness, TILE_SIZE, shelf_thickness))
        
        # Draw vertical supports on sides
        support_width = max(2, TILE_SIZE // 15)
        pygame.draw.rect(texture, shelf_color, (0, 0, support_width, TILE_SIZE))
        pygame.draw.rect(texture, shelf_color, (TILE_SIZE - support_width, 0, support_width, TILE_SIZE))
        
        # Draw middle shelf (if tile is tall enough)
        if TILE_SIZE > 60:
            mid_y = TILE_SIZE // 2
            pygame.draw.rect(texture, shelf_color, (0, mid_y - shelf_thickness // 2, TILE_SIZE, shelf_thickness))
        
        # Draw some product boxes on the shelf
        # Top shelf products
        if TILE_SIZE > 40:
            # Small boxes
            box_size = max(8, TILE_SIZE // 8)
            box_spacing = box_size + 2
            
            # Top row of boxes
            for i in range(2):
                box_x = support_width + 5 + i * box_spacing
                box_y = shelf_thickness + 3
                if box_x + box_size < TILE_SIZE - support_width:
                    # Box color (various product colors)
                    box_colors = [
                        (200, 50, 50),    # Red
                        (50, 150, 200),   # Blue
                        (200, 200, 50),   # Yellow
                        (150, 200, 50),   # Green
                    ]
                    box_color = box_colors[i % len(box_colors)]
                    pygame.draw.rect(texture, box_color, (box_x, box_y, box_size, box_size))
                    # Box highlight
                    pygame.draw.rect(texture, (min(255, box_color[0] + 30), 
                                             min(255, box_color[1] + 30), 
                                             min(255, box_color[2] + 30)), 
                                   (box_x, box_y, box_size, box_size // 3))
            
            # Bottom row of boxes (if there's a middle shelf)
            if TILE_SIZE > 60:
                for i in range(2):
                    box_x = support_width + 5 + i * box_spacing
                    box_y = TILE_SIZE // 2 + shelf_thickness // 2 + 3
                    if box_x + box_size < TILE_SIZE - support_width:
                        box_colors = [
                            (200, 50, 50),
                            (50, 150, 200),
                            (200, 200, 50),
                            (150, 200, 50),
                        ]
                        box_color = box_colors[(i + 2) % len(box_colors)]
                        pygame.draw.rect(texture, box_color, (box_x, box_y, box_size, box_size))
                        pygame.draw.rect(texture, (min(255, box_color[0] + 30), 
                                                 min(255, box_color[1] + 30), 
                                                 min(255, box_color[2] + 30)), 
                                       (box_x, box_y, box_size, box_size // 3))
        
        return texture
    
    def _generate_stone_wall_texture(self) -> pygame.Surface:
        """
        Generate a solid blue wall with no texture.
        
        Returns:
            A pygame Surface with the solid blue wall color
        """
        from config import TILE_SIZE, COLOR_WALL
        
        # Create surface for wall texture
        texture = pygame.Surface((TILE_SIZE, TILE_SIZE))
        
        # Just fill with solid blue color - no texture
        texture.fill(COLOR_WALL)
        
        return texture
    
    def _generate_door_texture(self) -> pygame.Surface:
        """
        Generate a wooden door texture.
        
        Returns:
            A pygame Surface with the door texture
        """
        from config import TILE_SIZE, COLOR_DOOR
        
        texture = pygame.Surface((TILE_SIZE, TILE_SIZE))
        base_color = COLOR_DOOR  # (120, 80, 40) brown
        texture.fill(base_color)
        
        # Draw door panels/boards
        darker_wood = (max(0, base_color[0] - 15), max(0, base_color[1] - 10), max(0, base_color[2] - 5))
        lighter_wood = (min(255, base_color[0] + 10), min(255, base_color[1] + 8), min(255, base_color[2] + 5))
        
        # Vertical door boards
        board_width = max(4, TILE_SIZE // 6)
        for i in range(0, TILE_SIZE, board_width + 2):
            board_color = lighter_wood if (i // (board_width + 2)) % 2 == 0 else darker_wood
            pygame.draw.rect(texture, board_color, (i, 0, board_width, TILE_SIZE))
        
        # Door handle/knob
        handle_size = max(3, TILE_SIZE // 15)
        handle_x = TILE_SIZE - handle_size - max(2, TILE_SIZE // 10)
        handle_y = TILE_SIZE // 2
        pygame.draw.circle(texture, (60, 60, 60), (handle_x, handle_y), handle_size)
        
        # Wood grain lines
        grain_color = (max(0, base_color[0] - 8), max(0, base_color[1] - 5), max(0, base_color[2] - 3))
        for i in range(0, TILE_SIZE, 4):
            if i % 8 == 0:
                pygame.draw.line(texture, grain_color, (0, i), (TILE_SIZE, i), 1)
        
        return texture
    
    def _generate_office_door_texture(self) -> pygame.Surface:
        """
        Generate a darker wooden office door texture.
        
        Returns:
            A pygame Surface with the office door texture
        """
        from config import TILE_SIZE, COLOR_OFFICE_DOOR
        
        texture = pygame.Surface((TILE_SIZE, TILE_SIZE))
        base_color = COLOR_OFFICE_DOOR  # (80, 50, 25) darker brown
        texture.fill(base_color)
        
        # Draw door panels/boards
        darker_wood = (max(0, base_color[0] - 12), max(0, base_color[1] - 8), max(0, base_color[2] - 4))
        lighter_wood = (min(255, base_color[0] + 8), min(255, base_color[1] + 6), min(255, base_color[2] + 4))
        
        # Vertical door boards
        board_width = max(4, TILE_SIZE // 6)
        for i in range(0, TILE_SIZE, board_width + 2):
            board_color = lighter_wood if (i // (board_width + 2)) % 2 == 0 else darker_wood
            pygame.draw.rect(texture, board_color, (i, 0, board_width, TILE_SIZE))
        
        # Door handle/knob
        handle_size = max(3, TILE_SIZE // 15)
        handle_x = TILE_SIZE - handle_size - max(2, TILE_SIZE // 10)
        handle_y = TILE_SIZE // 2
        pygame.draw.circle(texture, (40, 40, 40), (handle_x, handle_y), handle_size)
        
        # Wood grain lines
        grain_color = (max(0, base_color[0] - 6), max(0, base_color[1] - 4), max(0, base_color[2] - 2))
        for i in range(0, TILE_SIZE, 4):
            if i % 8 == 0:
                pygame.draw.line(texture, grain_color, (0, i), (TILE_SIZE, i), 1)
        
        return texture
    
    def _generate_counter_texture(self) -> pygame.Surface:
        """
        Generate a glass display counter texture.
        
        Returns:
            A pygame Surface with the glass counter texture
        """
        from config import TILE_SIZE, COLOR_COUNTER
        
        texture = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        
        # Glass base color - light blue/cyan with transparency
        glass_base = (180, 220, 255, 200)  # Light blue with alpha
        glass_darker = (150, 190, 240, 220)  # Slightly darker for edges
        
        # Fill with glass base color
        texture.fill(glass_base)
        
        # Draw glass frame/edges (darker)
        frame_thickness = max(2, TILE_SIZE // 15)
        # Top edge
        pygame.draw.rect(texture, glass_darker, (0, 0, TILE_SIZE, frame_thickness))
        # Bottom edge
        pygame.draw.rect(texture, glass_darker, (0, TILE_SIZE - frame_thickness, TILE_SIZE, frame_thickness))
        # Left and right edges
        pygame.draw.rect(texture, glass_darker, (0, 0, frame_thickness, TILE_SIZE))
        pygame.draw.rect(texture, glass_darker, (TILE_SIZE - frame_thickness, 0, frame_thickness, TILE_SIZE))
        
        return texture
    
    def _draw_boss_fight_menu(self, x: int, y: int, spacing: int, selection: int, fight_options: list[dict]) -> None:
        """
        Draw the boss fight menu buttons.
        
        Args:
            x: X position of button group (left side)
            y: Y position of first button (top)
            spacing: Vertical spacing between buttons
            selection: Currently selected button index (0 = Fight, 1 = Bag, 2 = Pay)
        """
        buttons = fight_options if fight_options else [
            {"label": "Logic", "enabled": True},
            {"label": "Nuke", "enabled": False},
            {"label": "Water Gun", "enabled": False},
            {"label": "Paper Plane", "enabled": False},
        ]
        bold_font = pygame.font.SysFont(None, 108)  # 3x bigger (36 * 3 = 108)
        bold_font.set_bold(True)
        text_color = (255, 255, 255)  # White text
        selected_color = (255, 255, 100)  # Yellow for selected
        disabled_color = (140, 140, 140)
        
        for i, button_data in enumerate(buttons):
            label = button_data.get("label", "Option")
            enabled = button_data.get("enabled", False)
            button_y = y + (i * spacing)
            is_selected = (i == selection)
            
            # Draw selection indicator ">" (3x bigger spacing)
            if is_selected:
                indicator = bold_font.render(">", True, selected_color)
                self.screen.blit(indicator, (x - 75, button_y))  # 3x spacing (25 * 3 = 75)
            
            # Draw button text
            base_color = selected_color if is_selected else (text_color if enabled else disabled_color)
            text_surface = bold_font.render(label, True, base_color)
            self.screen.blit(text_surface, (x, button_y))

    def _draw_computer_light(self, rect: pygame.Rect, idx: int = 0) -> None:
        """Draw a color-cycling outline over a computer tile, keeping PNG visible."""
        colors = [
            (255, 80, 80),
            (255, 200, 80),
            (120, 255, 120),
            (80, 220, 255),
            (180, 120, 255),
            (255, 120, 200),
        ]
        # Add per-computer phase offset to desync lights
        t = (pygame.time.get_ticks() + idx * 413) / 300.0
        idx = int(t) % len(colors)
        next_idx = (idx + 1) % len(colors)
        frac = t - int(t)
        c1 = colors[idx]
        c2 = colors[next_idx]
        blend = tuple(int(c1[i] * (1 - frac) + c2[i] * frac) for i in range(3))
        surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(surface, (*blend, 140), surface.get_rect(), width=6, border_radius=8)
        self.screen.blit(surface, rect.topleft)
    
    def _initialize_falling_cash(self) -> None:
        """Initialize falling cash items for main menu background."""
        import random
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        # Create 30-40 falling cash items (2x more)
        num_cash = random.randint(30, 40)
        self.falling_cash = []
        
        for _ in range(num_cash):
            x = random.randint(0, screen_width)
            y = random.randint(-screen_height, 0)  # Start above screen
            speed = random.uniform(50.0, 150.0)  # Pixels per second
            angle = random.uniform(0, 360)  # Initial rotation angle in degrees
            rotation_speed = random.uniform(-180.0, 180.0)  # Rotation speed in degrees per second
            size_scale = random.uniform(0.7, 1.3)  # Size variation (70% to 130%)
            self.falling_cash.append({
                "pos": pygame.Vector2(x, y),
                "speed": speed,
                "angle": angle,
                "rotation_speed": rotation_speed,
                "size_scale": size_scale
            })
    
    def _update_falling_cash(self, dt: float) -> None:
        """Update falling cash positions and rotations."""
        import random
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        for cash in self.falling_cash:
            # Move cash down
            cash["pos"].y += cash["speed"] * dt
            
            # Rotate coin
            cash["angle"] += cash["rotation_speed"] * dt
            cash["angle"] %= 360  # Keep angle in 0-360 range
            
            # Respawn at top if fallen off screen
            if cash["pos"].y > screen_height + 50:
                cash["pos"].x = random.randint(0, screen_width)
                cash["pos"].y = random.randint(-200, -50)
                cash["speed"] = random.uniform(50.0, 150.0)
                cash["angle"] = random.uniform(0, 360)
                cash["rotation_speed"] = random.uniform(-180.0, 180.0)
                cash["size_scale"] = random.uniform(0.7, 1.3)
    


    def draw_main_menu(self, dt: float = 0.016, text_alpha: int = 255, show_flash: bool = False, flash_timer: float = 0.0, flash_duration: float = 0.3, cash_alpha: int | None = None) -> None:
        """
        Draw the main menu with pixelated title and play button (no borders).
        
        Args:
            dt: Delta time in seconds for animating falling cash
            text_alpha: Alpha value for text (255 = fully visible, 0 = invisible)
            show_flash: Whether to show flash effect
            flash_timer: Current flash timer value
            flash_duration: Total flash duration in seconds
        """
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        # If flash is active, ONLY draw the flash - nothing else
        if show_flash and flash_timer < flash_duration * 2:
            # Calculate flash intensity (starts bright, fades out over 2x duration)
            progress = flash_timer / (flash_duration * 2)  # Use 2x duration for smoother fade
            # Fade from 255 to 0 over the duration (ease out curve)
            fade_progress = 1.0 - (progress * progress)  # Quadratic ease out
            flash_alpha = int(255 * fade_progress)
            
            # Fill screen with white flash
            flash_surface = pygame.Surface((screen_width, screen_height))
            flash_surface.fill((255, 255, 255))
            flash_surface.set_alpha(flash_alpha)
            self.screen.fill(COLOR_BG)  # Fill background first
            self.screen.blit(flash_surface, (0, 0))
            return  # Exit early - don't draw menu elements
        
        # Normal menu rendering (when not flashing)
        # Initialize falling cash if empty (in case screen wasn't ready during __init__)
        if not self.falling_cash:
            self._initialize_falling_cash()
        
        # Update falling cash
        self._update_falling_cash(dt)
        
        # Fill with background color
        self.screen.fill(COLOR_BG)
        
        # Draw falling cash in background (as 3D coins)
        from config import COLOR_CASH, TILE_SIZE
        base_radius = TILE_SIZE // 4  # Base radius for coin (2x bigger)
        coin_alpha = text_alpha if cash_alpha is None else cash_alpha
        
        for cash in self.falling_cash:
            # Calculate coin size based on scale
            coin_radius = int(base_radius * cash["size_scale"])
            
            # Only draw if on screen
            if -coin_radius <= cash["pos"].y <= screen_height + coin_radius:
                # Calculate perspective effect based on angle (0-90 degrees = face-on, 90-180 = edge-on)
                # Use sin to create 3D effect: when angle is 0 or 180, coin is face-on (full size)
                # When angle is 90 or 270, coin is edge-on (smaller)
                angle_rad = math.radians(cash["angle"])
                perspective_scale = abs(math.cos(angle_rad))  # 1.0 when face-on, 0.0 when edge-on
                perspective_scale = max(0.3, perspective_scale)  # Minimum 30% size for visibility
                
                # Calculate ellipse dimensions for 3D effect
                # When face-on: width = height = full radius
                # When edge-on: width = small, height = full radius
                ellipse_width = int(coin_radius * 2 * perspective_scale)
                ellipse_height = int(coin_radius * 2)
                
                # Create a surface for the coin to rotate it
                coin_surface_size = int(coin_radius * 2 * 1.5)  # Extra space for rotation
                coin_surface = pygame.Surface((coin_surface_size, coin_surface_size), pygame.SRCALPHA)
                coin_surface.set_alpha(coin_alpha)
                
                # Draw coin base (circle/ellipse) with 3D shading
                coin_center = (coin_surface_size // 2, coin_surface_size // 2)
                
                # Main coin color (brighter on top for 3D effect)
                main_color = COLOR_CASH
                # Darker shade for bottom/edge
                dark_color = (
                    max(0, COLOR_CASH[0] - 40),
                    max(0, COLOR_CASH[1] - 40),
                    max(0, COLOR_CASH[2] - 40)
                )
                
                # Draw coin as ellipse (rotated)
                # Draw darker bottom half for 3D effect
                if perspective_scale > 0.5:  # Only show 3D effect when not edge-on
                    pygame.draw.ellipse(coin_surface, dark_color, 
                                      (coin_surface_size // 2 - ellipse_width // 2,
                                       coin_surface_size // 2 - ellipse_height // 2 + ellipse_height // 3,
                                       ellipse_width, ellipse_height // 2))
                
                # Draw main coin
                pygame.draw.ellipse(coin_surface, main_color,
                                  (coin_surface_size // 2 - ellipse_width // 2,
                                   coin_surface_size // 2 - ellipse_height // 2,
                                   ellipse_width, ellipse_height))
                
                # Rotate the coin surface
                rotated_coin = pygame.transform.rotate(coin_surface, cash["angle"])
                rotated_rect = rotated_coin.get_rect(center=(int(cash["pos"].x), int(cash["pos"].y)))
                
                # Draw rotated coin
                self.screen.blit(rotated_coin, rotated_rect)
        
        # Draw pixelated title with alpha
        title_text = "Tax Evasion Simulator"
        
        # Create a small font and render at small size for pixelation
        # Use monospace font for better pixelated look
        # Base size is 40px, will be scaled 4x to 160px total
        small_font = pygame.font.SysFont("monospace", 40)
        # Create text surface with alpha
        small_surface = small_font.render(title_text, True, COLOR_TEXT)
        
        # Scale up without smoothing for pixelated effect
        # Scale factor of 4 makes text 4x bigger (40px -> 160px)
        scale_factor = 4
        pixelated_title = pygame.transform.scale(
            small_surface,
            (small_surface.get_width() * scale_factor, small_surface.get_height() * scale_factor)
        )
        
        # Apply alpha to title
        pixelated_title.set_alpha(text_alpha)
        
        # Center title higher up on screen
        title_rect = pixelated_title.get_rect(center=(screen_width // 2, screen_height // 5))
        self.screen.blit(pixelated_title, title_rect)
        
        # Draw play button (no borders, just text) with alpha
        play_text = "Play"
        
        # Create a smaller font for the button (base 36px, scaled 3x to 108px)
        button_font = pygame.font.SysFont("monospace", 36)
        button_small_surface = button_font.render(play_text, True, COLOR_TEXT)
        
        # Scale up for pixelated effect
        button_scale_factor = 3
        pixelated_button = pygame.transform.scale(
            button_small_surface,
            (button_small_surface.get_width() * button_scale_factor, button_small_surface.get_height() * button_scale_factor)
        )
        
        # Apply alpha to button
        pixelated_button.set_alpha(text_alpha)
        
        # Center play button below title
        button_rect = pixelated_button.get_rect(center=(screen_width // 2, screen_height // 2 + 100))
        self.screen.blit(pixelated_button, button_rect)


    def draw_transition_effect(self, phase: str, timer: float, duration: float) -> None:
        """
        Draw transition overlay (fade/flash).
        
        Args:
            phase: Current transition phase ("fade_out" or "flash")
            timer: Current timer value
            duration: Total duration of the phase
        """
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        overlay = pygame.Surface((screen_width, screen_height))
        progress = min(1.0, timer / duration)
        
        if phase == "fade_out":
            # Fade to black: alpha goes 0 -> 255
            alpha = int(255 * progress)
            overlay.fill((0, 0, 0))
        elif phase == "flash":
            # Flash white: alpha goes 255 -> 0 (fade in from white)
            # Main menu flash: White screen fades OUT.
            alpha = int(255 * (1.0 - progress))
            overlay.fill((255, 255, 255))
        else:
            return

        overlay.set_alpha(alpha)
        self.screen.blit(overlay, (0, 0))
