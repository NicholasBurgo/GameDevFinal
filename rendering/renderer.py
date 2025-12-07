"""Main renderer for game entities and map."""

import math
from typing import Union

import cv2
import numpy as np
import pygame

from config import COLOR_BG, COLOR_DAY_OVER_BG, COLOR_DAY_OVER_TEXT, COLOR_TEXT, DAY_DURATION
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

    def clear(self) -> None:
        """Clear the screen with background color."""
        self.screen.fill(COLOR_BG)

    def draw_map(self, tile_map: TileMap) -> None:
        """Draw the tile map."""
        tile_map.draw(self.screen)
    
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
                        COLOR_COUNTER, COLOR_DOOR, COLOR_FLOOR, COLOR_NODE,
                        COLOR_OFFICE_DOOR, COLOR_SHELF, COLOR_WALL, TILE_COUNTER,
                        TILE_DOOR, TILE_FLOOR, TILE_NODE, TILE_OFFICE_DOOR,
                        TILE_SHELF, TILE_WALL
                    )
                    
                    if tile == TILE_WALL:
                        color = COLOR_WALL
                    elif tile == TILE_SHELF:
                        color = COLOR_SHELF
                    elif tile == TILE_DOOR:
                        color = COLOR_DOOR
                    elif tile == TILE_OFFICE_DOOR:
                        color = COLOR_OFFICE_DOOR
                    elif tile == TILE_COUNTER:
                        color = COLOR_COUNTER
                    elif tile == TILE_NODE:
                        color = COLOR_FLOOR
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
                from config import COLOR_CUSTOMER
                pygame.draw.circle(self.screen, COLOR_CUSTOMER,
                                 (int(customer.position.x), int(customer_screen_y)),
                                 CUSTOMER_RADIUS)
        
        # Draw player with camera offset
        player_screen_y = player.y - int(camera_y_offset)
        screen_height = self.screen.get_height()
        from config import PLAYER_RADIUS
        if -PLAYER_RADIUS <= player_screen_y < screen_height + PLAYER_RADIUS:
            from config import COLOR_PLAYER
            pygame.draw.circle(self.screen, COLOR_PLAYER,
                             (int(player.x), int(player_screen_y)), PLAYER_RADIUS)
    
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

        # Draw player last so it appears on top
        player.draw(self.screen)

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
        boss_fight_triggered: bool = False
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
        """
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
        
        # Show "thinking" indicator if awaiting response
        if awaiting_response:
            thinking_y = current_y if current_y > conversation_start_y else conversation_start_y
            # Make sure thinking indicator is visible (within scrollable area)
            if thinking_y < input_box_top - 20:
                thinking_text = "Tax Dude is typing..."
                thinking_surface = small_font.render(thinking_text, True, (150, 150, 150))
                thinking_rect = thinking_surface.get_rect()
                thinking_rect.left = screen_x + left_margin
                thinking_rect.top = thinking_y
                if thinking_y > conversation_start_y:
                    self.screen.blit(thinking_surface, thinking_rect)
            current_y = thinking_y + 30
        
        # Always draw input box at the bottom (only if boss fight not triggered)
        if not boss_fight_triggered:
            input_box_height = 50
            input_box_margin = 10
            input_box_y = screen_y + screen_h - input_box_height - input_box_margin
            input_box_width = screen_w - 40
            input_box_x = screen_x + (screen_w - input_box_width) // 2
            
            # Draw input box background (white with border)
            input_box_rect = pygame.Rect(input_box_x, input_box_y, input_box_width, input_box_height)
            pygame.draw.rect(self.screen, (255, 255, 255), input_box_rect, border_radius=10)
            pygame.draw.rect(self.screen, (200, 200, 200), input_box_rect, width=2, border_radius=10)
            
            # Draw player's input text with cursor
            input_text = player_argument + "_"  # Cursor
            input_lines = self._wrap_text(input_text, input_font, input_box_width - 20, text_color)
            
            for i, line in enumerate(input_lines):
                line_surface = input_font.render(line, True, text_color)
                line_rect = line_surface.get_rect()
                line_rect.left = input_box_x + 15
                line_rect.centery = input_box_y + input_box_height // 2 + i * 24 - (len(input_lines) - 1) * 12
                self.screen.blit(line_surface, line_rect)
        
        # Instructions at very bottom
        if boss_fight_triggered:
            instruction = "Press SPACE to close"
        else:
            instruction = "Type a message and press ENTER to send. Click Venmo to pay. Press SPACE to close."
        instruction_surface = pygame.font.SysFont(None, 16).render(instruction, True, (150, 150, 150))
        instruction_rect = instruction_surface.get_rect(center=(screen_x + screen_w // 2, screen_y + screen_h - 2))
        self.screen.blit(instruction_surface, instruction_rect)
    
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
    
    def draw_boss_fight_screen(self, show_flash: bool = False, flash_timer: float = 0.0, flash_duration: float = 0.3, 
                               boss_health: float = 100.0, player_health: float = 100.0, menu_selection: int = 0) -> None:
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
        
        # Pokemon-style flash effect: bright white flash that fades out
        if show_flash and flash_timer < flash_duration:
            # Calculate flash intensity (starts at 255, fades to 0)
            progress = flash_timer / flash_duration
            # Use a curve for smoother fade (ease out)
            fade_progress = 1.0 - (progress * progress)  # Quadratic ease out
            flash_alpha = int(255 * fade_progress)
            
            # Create a white surface with alpha for the flash
            flash_surface = pygame.Surface((screen_width, screen_height))
            flash_surface.fill((255, 255, 255))
            flash_surface.set_alpha(flash_alpha)
            self.screen.blit(flash_surface, (0, 0))
        
        # Fallback if image not loaded
        if not battle_scene_drawn:
            self.screen.fill((0, 0, 0))
            large_font = pygame.font.SysFont(None, 72)
            text = "BOSS FIGHT INITIATED"
            text_surface = large_font.render(text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(screen_width // 2, screen_height // 2))
            self.screen.blit(text_surface, text_rect)
        
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
            
            # Draw menu buttons (Fight, Bag, Pay)
            # ===== MENU BUTTON POSITIONS (EASY TO ADJUST) =====
            MENU_BUTTONS_X = 1600 # 400 pixels from right edge (moved left)
            MENU_BUTTONS_Y = 1100 # 400 pixels from bottom (moved up)
            BUTTON_SPACING = 80  # Space between buttons (closer together)
            # =================================================
            self._draw_boss_fight_menu(MENU_BUTTONS_X, MENU_BUTTONS_Y, BUTTON_SPACING, menu_selection)
    
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
    
    def _draw_boss_fight_menu(self, x: int, y: int, spacing: int, selection: int) -> None:
        """
        Draw the boss fight menu buttons (Fight, Bag, Pay).
        
        Args:
            x: X position of button group (left side)
            y: Y position of first button (top)
            spacing: Vertical spacing between buttons
            selection: Currently selected button index (0 = Fight, 1 = Bag, 2 = Pay)
        """
        buttons = ["Fight", "Bag", "Pay"]
        bold_font = pygame.font.SysFont(None, 108)  # 3x bigger (36 * 3 = 108)
        bold_font.set_bold(True)
        text_color = (255, 255, 255)  # White text
        selected_color = (255, 255, 100)  # Yellow for selected
        
        for i, button_text in enumerate(buttons):
            button_y = y + (i * spacing)
            is_selected = (i == selection)
            
            # Draw selection indicator ">" (3x bigger spacing)
            if is_selected:
                indicator = bold_font.render(">", True, selected_color)
                self.screen.blit(indicator, (x - 75, button_y))  # 3x spacing (25 * 3 = 75)
            
            # Draw button text
            color = selected_color if is_selected else text_color
            text_surface = bold_font.render(button_text, True, color)
            self.screen.blit(text_surface, (x, button_y))

