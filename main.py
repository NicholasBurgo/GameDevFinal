"""Main entry point for the game."""

import sys

import pygame

import pygame

from config import FPS, TILE_SIZE
from game import GameState
from map import TileMap
from rendering import HUD, Renderer


def main() -> None:
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Pygame Store - Tile World")
    
    # Initialize sound mixer
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    except pygame.error:
        print("Warning: Could not initialize audio mixer")
    
    # Create tile map (initial - GameState will create both maps)
    tile_map = TileMap()
    
    # Initialize game systems first to get both maps
    game_state = GameState(tile_map)
    
    # Screen size based on the larger room (usually store)
    store_width = game_state.store_map.cols * TILE_SIZE
    store_height = game_state.store_map.rows * TILE_SIZE
    office_width = game_state.office_map.cols * TILE_SIZE
    office_height = game_state.office_map.rows * TILE_SIZE
    
    screen_width = max(store_width, office_width)
    screen_height = max(store_height, office_height)
    
    screen = pygame.display.set_mode((screen_width, screen_height))
    clock = pygame.time.Clock()

    # Load day over sound
    day_over_sound = None
    try:
        # Try loading as webm - may need conversion if pygame doesn't support it
        sound_path = "assets/sounds/Dayoversound.webm"
        day_over_sound = pygame.mixer.Sound(sound_path)
    except (pygame.error, FileNotFoundError):
        # If webm doesn't work, try to find a converted version or skip
        print(f"Warning: Could not load sound file {sound_path}. Pygame mixer may not support .webm files.")
        print("Consider converting the file to .wav or .ogg format.")

    # Initialize renderer
    renderer = Renderer(screen)
    hud = HUD()
    
    # Load day over video
    video_path = "assets/NextDay.mp4"
    video_loaded = renderer.load_day_over_video(video_path)
    if not video_loaded:
        print(f"Warning: Could not load video file: {video_path}")
        print("Day over screen will use fallback text animation.")
    
    # Store sound in game_state for easy access
    game_state.day_over_sound = day_over_sound

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0

        # Handle events
        for event in pygame.event.get():
            if game_state.handle_event(event, renderer=renderer):
                running = False

        # Update game state
        game_state.update(dt)

        # Render based on game state
        if game_state.game_state in ("playing", "waiting_for_customers", "collection_time", "tax_man_notification"):
            # Render normal game (allows player to move and collect during waiting/collection states)
            renderer.clear()
            # Draw active room with camera offset
            active_map = game_state.store_map if game_state.current_room == "store" else game_state.office_map
            room_world_y_offset = 0.0 if game_state.current_room == "store" else game_state.office_world_y_offset
            renderer.draw_room_with_camera(
                active_map=active_map,
                camera_y_offset=game_state.camera_y_offset,
                player=game_state.player,
                customers=game_state.customers if game_state.current_room == "store" else [],
                cash_items=game_state.cash_items if game_state.current_room == "store" else [],
                litter_items=game_state.litter_items if game_state.current_room == "store" else [],
                room_world_y_offset=room_world_y_offset,
            )
            
            # Draw pixelated time counter at top center
            renderer.draw_time_counter(game_state.current_day, game_state.day_timer)
            
            # Draw pixelated coins counter at top right
            renderer.draw_coins_counter(game_state.collected_coins)
            
            # Draw tax man notification if in notification state
            if game_state.game_state == "tax_man_notification":
                renderer.draw_tax_man_notification(game_state.tax_man_tax_amount)
            
            # Update HUD lines with game info
            hud_lines = [
                "Use WASD or arrow keys to move.",
                "Press I to end the day early.",
                "ESC or window close to quit.",
            ]
            if game_state.game_state == "waiting_for_customers":
                hud_lines.append("Waiting for customers to leave...")
            elif game_state.game_state == "collection_time":
                remaining_time = max(0, 5.0 - game_state.collection_timer)
                hud_lines.append(f"Collection time: {remaining_time:.1f}s")
            elif game_state.game_state == "tax_man_notification":
                hud_lines.append("Press SPACE to open message")
            
            hud.draw(screen, hud_lines)
        elif game_state.game_state == "day_over_animation":
            # Render animated day over screen with video
            video_playing = renderer.draw_day_over_screen(game_state.current_day, video_playing=game_state.video_playing, dt=dt)
            # Update game state to track if video finished
            game_state.video_playing = video_playing
        elif game_state.game_state == "day_over":
            # Legacy day over screen (for backwards compatibility)
            renderer.draw_day_over_screen(game_state.current_day, video_playing=False, dt=dt)
        elif game_state.game_state == "tax_man":
            # Render tax man screen
            renderer.draw_tax_man_screen(
                tax_amount=game_state.tax_man_tax_amount,
                menu_selection=game_state.tax_man_menu_selection,
                ai_response=game_state.tax_man_ai_response,
                awaiting_response=game_state.tax_man_awaiting_response,
                input_mode=game_state.tax_man_input_mode,
                player_argument=game_state.tax_man_player_argument,
                conversation=game_state.tax_man_conversation,
                boss_fight_triggered=game_state.tax_man_boss_fight_triggered
            )
        elif game_state.game_state == "boss_fight":
            # Render boss fight screen
            renderer.draw_boss_fight_screen()

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
