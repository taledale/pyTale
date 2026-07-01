"""Type wrapper for the server-wide universe API"""

from uuid import UUID

import java as _java
from pytale._java_wrapper import JavaWrapper
from pytale._uuid import python_uuid_to_java
from pytale.message import Message, MessageLike
from pytale.players import PlayerRef
from pytale.world._types import World

_Message = _java.type("com.hypixel.hytale.server.core.Message")
_NameMatching = _java.type("com.hypixel.hytale.server.core.NameMatching")


class Universe(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.universe.Universe.

    The universe is a process-wide singleton that owns every loaded world and
    connected player, so it can be reached from any execution context (see
    ``get_universe``).

    Worlds returned from here are real ``World`` wrappers: most methods (reads,
    ticking/paused setters, ``send_message``) work here, but block access and
    ``set_tps`` must run on that world's thread and raise
    ``pytale.world.NotInWorldThreadError`` if called in this context.
    """

    # --- read-only properties ---

    @property
    def player_count(self) -> int:
        """Total number of players connected across all worlds."""
        return self._java.getPlayerCount()

    @property
    def worlds(self) -> list[World]:
        """All currently loaded worlds."""
        return [World(world) for world in self._java.getWorlds().values()]

    @property
    def players(self) -> tuple[PlayerRef, ...]:
        """All currently connected players, across every world."""
        return tuple(PlayerRef(player) for player in self._java.getPlayers())

    # --- lookups ---

    def get_world(self, name: str) -> World | None:
        """Return the world with the given name, or None if not loaded."""
        world = self._java.getWorld(name)
        return World(world) if world is not None else None

    def get_world_by_uuid(self, uuid: UUID) -> World | None:
        """Return the world with the given UUID, or None if not loaded."""
        world = self._java.getWorld(python_uuid_to_java(uuid))
        return World(world) if world is not None else None

    def get_default_world(self) -> World | None:
        """Return the configured default world, or None if unavailable."""
        world = self._java.getDefaultWorld()
        return World(world) if world is not None else None

    def get_player(self, uuid: UUID) -> PlayerRef | None:
        """Return the connected player with the given UUID, or None."""
        player = self._java.getPlayer(python_uuid_to_java(uuid))
        return PlayerRef(player) if player is not None else None

    def get_player_by_name(self, name: str) -> PlayerRef | None:
        """Return the connected player with the given username, or None.

        Matching is case-insensitive but otherwise exact.
        """
        player = self._java.getPlayerByUsername(name, _NameMatching.EXACT_IGNORE_CASE)
        return PlayerRef(player) if player is not None else None

    # --- other methods ---

    def send_message(self, message: MessageLike) -> None:
        """Broadcast a message to every connected player."""
        if isinstance(message, Message):
            self._java.sendMessage(message._java)
        else:
            self._java.sendMessage(_Message.raw(message))

    def __repr__(self) -> str:
        return f"Universe(worlds={len(self.worlds)}, players={self.player_count})"
