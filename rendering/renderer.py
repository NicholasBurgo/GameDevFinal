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

    def clear(self) -> None:
        """Clear the screen with background color."""
        self.screen.fill(COLOR_BG)

    def draw_map(self, tile_map: TileMap) -> None:
        """Draw the tile map."""
        tile_map.draw(self.screen)

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

    def draw_tax_man_screen(
        self, 
        tax_amount: int, 
        menu_selection: int = 0,
        ai_response: str | None = None,
        awaiting_response: bool = False,
        input_mode: bool = False,
        player_argument: str = ""
    ) -> None:
        """
        Draw tax man screen with menu options.
        
        Args:
            tax_amount: Amount of tax to pay
            menu_selection: Currently selected menu option (0 = Pay, 1 = Argue)
            ai_response: AI-generated response if player argued
            awaiting_response: Whether waiting for AI response
            input_mode: Whether player is typing their argument
            player_argument: The text the player has typed
        """
        # Fill with black background
        self.screen.fill(COLOR_DAY_OVER_BG)
        
        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()
        
        # Create font for the tax man text
        large_font = pygame.font.SysFont(None, 48)
        medium_font = pygame.font.SysFont(None, 36)
        small_font = pygame.font.SysFont(None, 24)
        
        # Title
        title_text = "The Tax Man Arrives..."
        title_surface = large_font.render(title_text, True, COLOR_DAY_OVER_TEXT)
        title_rect = title_surface.get_rect(center=(screen_width // 2, screen_height // 4))
        self.screen.blit(title_surface, title_rect)
        
        # Tax amount
        tax_text = f"Tax Due: {tax_amount} coins"
        tax_surface = medium_font.render(tax_text, True, COLOR_DAY_OVER_TEXT)
        tax_rect = tax_surface.get_rect(center=(screen_width // 2, screen_height // 4 + 60))
        self.screen.blit(tax_surface, tax_rect)
        
        # Show AI response if available
        if ai_response:
            # Draw AI response in a box
            response_y = screen_height // 2 - 40
            response_lines = self._wrap_text(ai_response, small_font, screen_width - 100)
            
            for i, line in enumerate(response_lines):
                line_surface = small_font.render(line, True, COLOR_DAY_OVER_TEXT)
                line_rect = line_surface.get_rect(center=(screen_width // 2, response_y + i * 30))
                self.screen.blit(line_surface, line_rect)
            
            # Instruction to continue
            instruction = "Press any key to continue..."
            instruction_surface = small_font.render(instruction, True, COLOR_DAY_OVER_TEXT)
            instruction_rect = instruction_surface.get_rect(center=(screen_width // 2, screen_height - 60))
            self.screen.blit(instruction_surface, instruction_rect)
        elif awaiting_response:
            # Show loading message
            loading_text = "The tax man is thinking..."
            loading_surface = small_font.render(loading_text, True, COLOR_DAY_OVER_TEXT)
            loading_rect = loading_surface.get_rect(center=(screen_width // 2, screen_height // 2))
            self.screen.blit(loading_surface, loading_rect)
        elif input_mode:
            # Draw text input box
            input_box_width = screen_width - 100
            input_box_height = 60
            input_box_x = (screen_width - input_box_width) // 2
            input_box_y = screen_height // 2 - 30
            
            # Draw input box background
            input_box_rect = pygame.Rect(input_box_x, input_box_y, input_box_width, input_box_height)
            pygame.draw.rect(self.screen, (40, 40, 40), input_box_rect)
            pygame.draw.rect(self.screen, COLOR_DAY_OVER_TEXT, input_box_rect, 2)
            
            # Draw prompt
            prompt_text = "State your argument:"
            prompt_surface = small_font.render(prompt_text, True, COLOR_DAY_OVER_TEXT)
            prompt_rect = prompt_surface.get_rect(center=(screen_width // 2, input_box_y - 30))
            self.screen.blit(prompt_surface, prompt_rect)
            
            # Draw player's input text with cursor
            input_text = player_argument + "_"  # Cursor
            # Wrap text if too long
            input_lines = self._wrap_text(input_text, small_font, input_box_width - 20)
            
            for i, line in enumerate(input_lines):
                line_surface = small_font.render(line, True, COLOR_DAY_OVER_TEXT)
                line_rect = line_surface.get_rect()
                line_rect.left = input_box_x + 10
                line_rect.centery = input_box_y + (i + 1) * (input_box_height // (len(input_lines) + 1))
                self.screen.blit(line_surface, line_rect)
            
            # Instructions
            instruction = "Type your argument, then press ENTER to submit (ESC to cancel)"
            instruction_surface = small_font.render(instruction, True, COLOR_DAY_OVER_TEXT)
            instruction_rect = instruction_surface.get_rect(center=(screen_width // 2, screen_height - 60))
            self.screen.blit(instruction_surface, instruction_rect)
        else:
            # Draw menu options
            menu_y = screen_height // 2
            options = ["Pay Tax", "Argue"]
            
            for i, option in enumerate(options):
                color = (255, 255, 0) if i == menu_selection else COLOR_DAY_OVER_TEXT
                option_text = f"{'> ' if i == menu_selection else '  '}{option}"
                option_surface = medium_font.render(option_text, True, color)
                option_rect = option_surface.get_rect(center=(screen_width // 2, menu_y + i * 50))
                self.screen.blit(option_surface, option_rect)
            
            # Instructions
            instruction = "Use UP/DOWN to select, ENTER to choose"
            instruction_surface = small_font.render(instruction, True, COLOR_DAY_OVER_TEXT)
            instruction_rect = instruction_surface.get_rect(center=(screen_width // 2, screen_height - 60))
            self.screen.blit(instruction_surface, instruction_rect)
    
    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            test_surface = font.render(test_line, True, COLOR_DAY_OVER_TEXT)
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

