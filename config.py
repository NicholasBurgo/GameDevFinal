"""Game configuration constants."""

import random

# Game settings
FPS = 60
DAY_DURATION = 25.0  # Duration of each day in seconds

# Base tile size, scaled up to make everything appear larger on screen.
TILE_SIZE = 40 * 3  # 3x bigger than the original

# Tile codes
TILE_FLOOR = "."
TILE_WALL = "#"
TILE_SHELF = "S"
TILE_DOOR = "D"
TILE_COUNTER = "C"
TILE_NODE = "N"  # Node that customers can buy from or walk to
TILE_OFFICE_DOOR = "O"  # Office door - only player can pass through
TILE_COMPUTER = "P"  # Computer tile in office
TILE_ACTIVATION = "A"  # Legacy activation tile
TILE_ACTIVATION_1 = "1"  # Computer 1 activation
TILE_ACTIVATION_2 = "2"  # Computer 2 activation
TILE_ACTIVATION_3 = "3"  # Computer 3 activation

# Colors
COLOR_BG = (15, 15, 25)
COLOR_FLOOR = (40, 40, 60)
COLOR_WALL = (30, 50, 120)  # Darker blue wall color
COLOR_SHELF = (140, 120, 80)
COLOR_DOOR = (120, 80, 40)  # brown door
COLOR_OFFICE_DOOR = (80, 50, 25)  # darker brown office door
COLOR_COUNTER = (240, 240, 240)  # white counter
COLOR_NODE = (100, 200, 255)  # light blue node
COLOR_COMPUTER = (60, 60, 80)  # dark gray computer
COLOR_CUSTOMER = (255, 140, 0)  # orange customers
COLOR_CASH = (60, 200, 60)
COLOR_LITTER = (150, 150, 150)  # gray litter
COLOR_PLAYER = (230, 230, 80)
COLOR_TEXT = (230, 230, 230)
COLOR_DAY_OVER_BG = (0, 0, 0)  # Black background for day over screen
COLOR_DAY_OVER_TEXT = (255, 255, 255)  # White text for day over screen
# Overlay opacity for subtly darkening floor tiles
FLOOR_OVERLAY_ALPHA = 60  # 0-255

# Player settings
PLAYER_RADIUS = 14 * 3
PLAYER_SPEED = 3.0 * 3

# Customer settings
CUSTOMER_RADIUS = PLAYER_RADIUS  # Same size as player
# Half the speed of the player
CUSTOMER_SPEED = PLAYER_SPEED / 2.0

# Collision sets
SOLID_TILES = {TILE_WALL, TILE_SHELF, TILE_DOOR, TILE_COUNTER, TILE_COMPUTER}
# Customers can pass through doors, but not walls, shelves, or counters
# Office doors block customers but not the player
# Nodes are walkable (customers can stand on them) and passable (no collision)
# Activation tiles are walkable like floor
CUSTOMER_SOLID_TILES = {TILE_WALL, TILE_SHELF, TILE_COUNTER, TILE_OFFICE_DOOR, TILE_COMPUTER}


def generate_random_customer_color() -> tuple[int, int, int]:
    """
    Generate a random color for customers, excluding player yellow and orange.
    
    Returns:
        RGB tuple (r, g, b) with values 0-255
    """
    excluded_colors = [
        COLOR_PLAYER,  # (230, 230, 80) - yellow
        COLOR_CUSTOMER,  # (255, 140, 0) - orange
    ]
    
    while True:
        # Generate random RGB values (avoid too dark colors for visibility)
        r = random.randint(50, 255)
        g = random.randint(50, 255)
        b = random.randint(50, 255)
        color = (r, g, b)
        
        # Check if color is not too close to excluded colors
        is_valid = True
        for excluded in excluded_colors:
            # Calculate color distance (simple euclidean distance)
            distance = ((r - excluded[0]) ** 2 + (g - excluded[1]) ** 2 + (b - excluded[2]) ** 2) ** 0.5
            if distance < 50:  # Too close to excluded color
                is_valid = False
                break
        
        if is_valid:
            return color

