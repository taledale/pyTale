"""Exceptions for the world API"""


class ChunkNotLoadedError(Exception):
    """Raised when a block operation targets a chunk that is not currently loaded"""

    def __init__(self, x: int, y: int, z: int) -> None:
        self.x = x
        self.y = y
        self.z = z
        super().__init__(f"Chunk for block ({x}, {y}, {z}) is not loaded")
