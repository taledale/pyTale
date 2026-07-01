"""Exceptions for the world API"""


class NotInWorldThreadError(RuntimeError):
    """Raised when a world operation that must run on the world thread is called
    from another thread.

    Most world methods are safe from any context, but get_block, set_block,
    break_block and set_tps must run on the world's own thread. This is raised
    when such a method is invoked on a World obtained outside its WORLD context
    (e.g. via the Universe in the general context)."""

    def __init__(self, world_name: str, operation: str) -> None:
        self.world_name = world_name
        self.operation = operation
        super().__init__(
            f"World.{operation} on {world_name!r} must run on its world thread "
            f"(not available in the current context)"
        )


class ChunkNotLoadedError(Exception):
    """Raised when a block operation targets a chunk that is not currently loaded"""

    def __init__(self, x: int, y: int, z: int) -> None:
        self.x = x
        self.y = y
        self.z = z
        super().__init__(f"Chunk for block ({x}, {y}, {z}) is not loaded")


class WorldNotAcceptingTasksError(RuntimeError):
    """Raised by World.execute() when the target world's tick thread has already
    stopped accepting tasks (world is shutting down or already stopped)."""

    def __init__(self, world_name: str) -> None:
        self.world_name = world_name
        super().__init__(
            f"World {world_name!r} is not accepting tasks (shutting down or already stopped)"
        )
