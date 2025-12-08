"""Main entry point for the game."""

import sys

import pygame

import pygame

from config import FPS, TILE_ACTIVATION, TILE_ACTIVATION_1, TILE_ACTIVATION_2, TILE_ACTIVATION_3, TILE_SIZE
from game import GameState
from map import TileMap
from rendering import HUD, Renderer


def main() -> None:
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Tax Evasion Simulator")
    
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

    # Load menu music and sounds
    select_sound = None
    try:
        select_sound = pygame.mixer.Sound("assets/sounds/Select.wav")
    except (pygame.error, FileNotFoundError):
        print("Warning: Could not load Select.wav")
    
    # Menu music (Menu.mp3) - this is the title screen music that loops
    menu_music_path = "assets/music/Menu.mp3"
    
    # In-shop music (InshopMusic.mp3) - plays during gameplay
    inshop_music_path = "assets/music/InshopMusic.mp3"
    
    # Load pickup coin sound
    pickup_coin_sound = None
    try:
        pickup_coin_sound = pygame.mixer.Sound("assets/sounds/pickupCoin.wav")
    except (pygame.error, FileNotFoundError):
        print("Warning: Could not load pickupCoin.wav")
    
    # Load hit sounds
    hit_sounds = []
    for i in range(1, 4):
        try:
            hit_sound = pygame.mixer.Sound(f"assets/sounds/HitS{i}.wav")
            hit_sounds.append(hit_sound)
        except (pygame.error, FileNotFoundError):
            print(f"Warning: Could not load HitS{i}.wav")

    # Initialize renderer
    renderer = Renderer(screen)
    hud = HUD()
    
    # Load day over video
    video_path = "assets/NextDay.mp4"
    video_loaded = renderer.load_day_over_video(video_path)
    if not video_loaded:
        print(f"Warning: Could not load video file: {video_path}")
        print("Day over screen will use fallback text animation.")
    
    # Store sounds in game_state for easy access
    game_state.day_over_sound = day_over_sound
    game_state.select_sound = select_sound
    game_state.menu_music_path = menu_music_path
    game_state.inshop_music_path = inshop_music_path
    game_state.pickup_coin_sound = pickup_coin_sound
    game_state.hit_sounds = hit_sounds
    
    # Load and store office music
    try:
        # Load as Sound to allow pausing main music channel while playing this
        game_state.office_music_sound = pygame.mixer.Sound("assets/music/ComputerScreen.mp3")
    except (pygame.error, FileNotFoundError) as e:
        print(f"Warning: Could not load ComputerScreen.mp3: {e}")
        game_state.office_music_sound = None

    # Load and store tax man music
    try:
        # Load as Sound to allow pausing main music channel while playing this
        game_state.tax_man_music_sound = pygame.mixer.Sound("assets/music/textingBoss.mp3")
    except (pygame.error, FileNotFoundError) as e:
        print(f"Warning: Could not load textingBoss.mp3: {e}")
        game_state.tax_man_music_sound = None

    # Load boss intro music
    try:
        game_state.boss_intro_sound = pygame.mixer.Sound("assets/music/bossIntro.mp3")
    except (pygame.error, FileNotFoundError) as e:
        print(f"Warning: Could not load bossIntro.mp3: {e}")
        game_state.boss_intro_sound = None
    
    # Start playing Menu.mp3 immediately - this is the title screen music that loops
    try:
        pygame.mixer.music.load(menu_music_path)
        pygame.mixer.music.play(-1)  # Loop indefinitely - title screen music
        game_state.menu_music_playing = True
        game_state.intro_music_playing = False
    except Exception as e:
        print(f"Warning: Could not load/play menu music: {e}")
        game_state.menu_music_playing = False
        game_state.intro_music_playing = False

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
        if game_state.game_state == "main_menu":
            # Render main menu (pass dt for falling cash animation, and menu state for fade/flash)
            renderer.draw_main_menu(
                dt=dt,
                text_alpha=game_state.menu_text_alpha,
                show_flash=game_state.menu_show_flash,
                flash_timer=game_state.menu_flash_timer,
                flash_duration=game_state.menu_flash_duration,
                cash_alpha=game_state.menu_text_alpha,
            )
        elif game_state.game_state in ("playing", "waiting_for_customers", "collection_time", "tax_man_notification", "boss_approaching"):
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
            
            # Draw orange circle if boss is approaching
            if game_state.game_state == "boss_approaching" and game_state.boss_circle_position is not None:
                renderer.draw_boss_approaching_circle(
                    circle_position=game_state.boss_circle_position,
                    circle_radius=game_state.boss_circle_radius,
                    camera_y_offset=game_state.camera_y_offset,
                )
            
            # Draw pixelated time counter at top center
            renderer.draw_time_counter(game_state.current_day, game_state.day_timer)
            
            # Draw pixelated coins counter at top right
            renderer.draw_coins_counter(game_state.collected_coins)
            
            # Draw tax man notification if in notification state
            if game_state.game_state == "tax_man_notification":
                renderer.draw_tax_man_notification(game_state.tax_man_tax_amount)
            
            # Update HUD lines with game info (only dynamic messages)
            hud_lines = []
            if game_state.game_state == "waiting_for_customers":
                hud_lines.append("Waiting for customers to leave...")
            elif game_state.game_state == "collection_time":
                remaining_time = max(0, 5.0 - game_state.collection_timer)
                hud_lines.append(f"Collection time: {remaining_time:.1f}s")
            elif game_state.game_state == "tax_man_notification":
                hud_lines.append("Press E to open message")
            elif (
                game_state.game_state == "playing"
                and game_state.current_room == "office"
                and game_state._get_player_tile() == TILE_ACTIVATION_1
            ):
                hud_lines.append("Press E to use computer slots")
            elif (
                game_state.game_state == "playing"
                and game_state.current_room == "office"
                and game_state._get_player_tile() == TILE_ACTIVATION_2
            ):
                hud_lines.append("Press E for mystery box")
            
            # Only draw HUD if there are messages to show
            if hud_lines:
                hud.draw(screen, hud_lines)
            
            # Draw transition effect (overlay everything)
            if game_state.transition_active:
                renderer.draw_transition_effect(
                    game_state.transition_phase,
                    game_state.transition_timer,
                    game_state.transition_duration
                )
        elif game_state.game_state == "mystery_box":
            # Use shared screen background when a computer UI is open
            computer_img = renderer.computer_screen_image

            renderer.draw_mystery_box_screen(
                coins=game_state.collected_coins,
                items=game_state.mystery_items,
                owned=game_state.mystery_inventory,
                message=game_state.mystery_message,
                last_item=game_state.mystery_last_item,
                nuke_triggered=game_state.mystery_nuke_triggered,
                computer_image=computer_img,
            )
        elif game_state.game_state == "rain_bet":
            # Use shared screen background when a computer UI is open
            computer_img = renderer.computer_screen_image
            renderer.draw_rain_bet_screen(computer_image=computer_img)
        elif game_state.game_state == "slot_machine":
            # Use shared screen background when a computer UI is open
            computer_img = renderer.computer_screen_image
            
            renderer.draw_slot_machine_screen(
                coins=game_state.collected_coins,
                bet=game_state.slot_bet,
                reels=game_state.slot_reels,
                message=game_state.slot_message,
                computer_image=computer_img,
            )
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
                boss_fight_triggered=game_state.tax_man_boss_fight_triggered,
                show_flash=game_state.tax_man_show_flash,
                flash_timer=game_state.tax_man_flash_timer,
                flash_duration=game_state.tax_man_flash_duration,
                fade_alpha=int(255 * (1.0 - (game_state.tax_man_fade_timer / game_state.tax_man_fade_duration))) if game_state.tax_man_fading_out else 255,
                menu_locked=game_state.tax_man_menu_locked
            )
        elif game_state.game_state == "boss_fight":
            # Render boss fight screen with Pokemon-style flash effect
            fight_options = game_state.get_boss_fight_options() if game_state.boss_fight_menu_mode == "fight" else None
            root_options = game_state.get_boss_root_options() if game_state.boss_fight_menu_mode != "fight" else None
            renderer.draw_boss_fight_screen(
                show_flash=game_state.boss_fight_show_flash,
                flash_timer=game_state.boss_fight_flash_timer,
                flash_duration=game_state.boss_fight_flash_duration,
                boss_health=game_state.boss_health,
                player_health=game_state.player_health,
                menu_selection=game_state.boss_fight_menu_selection,
                fight_options=fight_options if fight_options is not None else root_options,
                fight_prompt=game_state.boss_fight_prompt_visible,
            )

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
