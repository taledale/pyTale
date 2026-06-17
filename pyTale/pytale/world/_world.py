"""World access from the WORLD execution context"""

from typing import TYPE_CHECKING

from pytale.world._types import World

if TYPE_CHECKING:
    from java import JavaObject

__world: World | None = None


def _init_world(java_world: "JavaObject") -> None:
    """Called by Java during world context initialization"""
    global __world
    __world = World(java_world)


def get_world() -> World:
    """Get the World for the current execution context.

    Only available in the WORLD context; raises RuntimeError otherwise.
    """
    if __world is None:
        raise RuntimeError("World not available (not in a WORLD context)")
    return __world
