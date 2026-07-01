"""Type wrapper for the server-wide player handle"""

from uuid import UUID

import java as _java
from pytale._java_wrapper import JavaWrapper
from pytale._uuid import java_uuid_to_python
from pytale.message import Message, MessageLike

_Message = _java.type("com.hypixel.hytale.server.core.Message")


class PlayerRef(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.universe.PlayerRef.

    A PlayerRef is the persistent, server-wide handle for a connected player:
    identity, language, permissions, chat messaging, server referral, and a
    cached transform. It exists for as long as the player is connected, even
    between worlds, and is distinct from the world-thread-bound Player *entity*
    component (inventory, teleport, game mode), which is not exposed here.

    The whole surface below is safe to use from any execution context: it only
    reads cached fields or writes network packets. Obtain instances via
    ``get_universe().players`` / ``get_player`` / ``get_player_by_name`` or via
    ``World.players``.
    """

    # --- read-only properties ---

    @property
    def uuid(self) -> UUID:
        """The player's unique identifier."""
        return java_uuid_to_python(self._java.getUuid())

    @property
    def username(self) -> str:
        """The player's username."""
        return self._java.getUsername()

    @property
    def world_uuid(self) -> UUID | None:
        """UUID of the world the player is currently in, or None if not in one."""
        world_uuid = self._java.getWorldUuid()
        return java_uuid_to_python(world_uuid) if world_uuid is not None else None

    @property
    def is_valid(self) -> bool:
        """Whether this reference still points at a live player."""
        return self._java.isValid()

    @property
    def position(self) -> tuple[float, float, float]:
        """The player's (x, y, z) position.

        This is read from the player's cached transform, which is updated on the
        world thread as the player moves; off-thread it may be slightly stale.
        """
        position = self._java.getTransform().getPosition()
        return (float(position.x), float(position.y), float(position.z))

    @property
    def rotation(self) -> tuple[float, float, float]:
        """The player's (pitch, yaw, roll) rotation in degrees.

        Read from the cached transform; see ``position`` for staleness notes.
        """
        rotation = self._java.getTransform().getRotation()
        return (float(rotation.x), float(rotation.y), float(rotation.z))

    # --- read/write properties ---

    @property
    def language(self) -> str:
        """The player's preferred language."""
        return self._java.getLanguage()

    @language.setter
    def language(self, value: str) -> None:
        self._java.setLanguage(value)

    # --- other methods ---

    def send_message(self, message: MessageLike) -> None:
        """Send a chat message to this player."""
        if isinstance(message, Message):
            self._java.sendMessage(message._java)
        else:
            self._java.sendMessage(_Message.raw(message))

    def has_permission(self, permission_id: str, default: bool | None = None) -> bool:
        """Return whether the player has the given permission.

        When ``default`` is given it is returned for permissions that are not
        explicitly set; otherwise the server's own default is used.
        """
        if default is None:
            return self._java.hasPermission(permission_id)
        return self._java.hasPermission(permission_id, default)

    def refer_to_server(self, host: str, port: int) -> None:
        """Refer this player to another server at the given host and port."""
        self._java.referToServer(host, port)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PlayerRef) and other.uuid == self.uuid

    def __hash__(self) -> int:
        return hash(self.uuid)

    def __repr__(self) -> str:
        return f"PlayerRef(username={self.username!r}, uuid={self.uuid})"
