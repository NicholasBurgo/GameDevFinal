"""Game configuration constants."""

# Game settings
FPS = 60
DAY_DURATION = 45.0  # Duration of each day in seconds

# Base tile size, scaled up to make everything appear larger on screen.
TILE_SIZE = 40 * 3  # 3x bigger than the original

# Tile codes
TILE_FLOOR = "."
TILE_WALL = "#"
TILE_SHELF = "S"
TILE_DOOR = "D"
TILE_COUNTER = "C"
TILE_NODE = "N"  # Node that customers can buy from or walk to

# Colors
COLOR_BG = (15, 15, 25)
COLOR_FLOOR = (40, 40, 60)
COLOR_WALL = (90, 90, 130)
COLOR_SHELF = (140, 120, 80)
COLOR_DOOR = (120, 80, 40)  # brown door
COLOR_COUNTER = (240, 240, 240)  # white counter
COLOR_NODE = (100, 200, 255)  # light blue node
COLOR_CUSTOMER = (255, 140, 0)  # orange customers
COLOR_CASH = (60, 200, 60)
COLOR_LITTER = (150, 150, 150)  # gray litter
COLOR_PLAYER = (230, 230, 80)
COLOR_TEXT = (230, 230, 230)
COLOR_DAY_OVER_BG = (0, 0, 0)  # Black background for day over screen
COLOR_DAY_OVER_TEXT = (255, 255, 255)  # White text for day over screen

# Player settings
PLAYER_RADIUS = 14 * 3
PLAYER_SPEED = 3.0 * 3

# Customer settings
CUSTOMER_RADIUS = PLAYER_RADIUS  # Same size as player
# Half the speed of the player
CUSTOMER_SPEED = PLAYER_SPEED / 2.0

# Collision sets
SOLID_TILES = {TILE_WALL, TILE_SHELF, TILE_DOOR, TILE_COUNTER}
# Customers can pass through doors, but not walls, shelves, or counters
# Nodes are walkable (customers can stand on them) and passable (no collision)
CUSTOMER_SOLID_TILES = {TILE_WALL, TILE_SHELF, TILE_COUNTER}

