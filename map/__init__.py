"""Map system module."""

from .collision import get_customer_solid_tiles_around, get_solid_tiles_around
from .tile_map import TileMap

__all__ = ["TileMap", "get_solid_tiles_around", "get_customer_solid_tiles_around"]

