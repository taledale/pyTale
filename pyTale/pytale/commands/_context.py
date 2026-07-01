from typing import TYPE_CHECKING, Any
from uuid import UUID

import java as _java
from pytale._java_wrapper import JavaWrapper
from pytale.message import Message, MessageLike
from pytale.players import PlayerRef
from pytale.world._types import World

if TYPE_CHECKING:
    from java import JavaObject

_JMessage = _java.type("com.hypixel.hytale.server.core.Message")
_JPlayerRef = _java.type("com.hypixel.hytale.server.core.universe.PlayerRef")

_SENTINEL = object()


class CommandSender(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.command.system.CommandSender.

    Represents the entity that executed a command — either a player or the
    server console. Safe to use from any execution context.
    """

    @property
    def username(self) -> str:
        return self._java.getUsername()

    @property
    def uuid(self) -> UUID | None:
        raw = self._java.getUuid()
        return UUID(str(raw)) if raw is not None else None

    @property
    def is_player(self) -> bool:
        return getattr(_JPlayerRef, "class").isInstance(self._java)

    def has_permission(self, permission: str) -> bool:
        return self._java.hasPermission(permission)

    def send_message(self, message: MessageLike) -> None:
        if isinstance(message, Message):
            self._java.sendMessage(message._java)
        else:
            self._java.sendMessage(_JMessage.raw(message))

    def as_player(self) -> PlayerRef:
        if not self.is_player:
            raise TypeError("CommandSender is not a player")
        return PlayerRef(self._java)

    def __repr__(self) -> str:
        return f"CommandSender(username={self.username!r})"


class CommandContext(JavaWrapper):
    """Unified command context for all command types.

    Wraps the Java ``PythonCommandContext`` which provides string-based
    argument lookup and optional world/player references depending on the
    command type.
    """

    def __init__(self, java_ctx: "JavaObject") -> None:
        super().__init__(java_ctx)
        self._sender: CommandSender | None = None
        self._world: World | None = None
        self._player_ref: PlayerRef | None = None
        self._world_resolved = False
        self._player_resolved = False

    @property
    def sender(self) -> CommandSender:
        if self._sender is None:
            self._sender = CommandSender(self._java.sender())
        return self._sender

    @property
    def is_player(self) -> bool:
        return self._java.isPlayer()

    @property
    def world(self) -> World | None:
        if not self._world_resolved:
            java_world = self._java.getWorld()
            if java_world is not None:
                self._world = World(java_world)
            self._world_resolved = True
        return self._world

    @property
    def player_ref(self) -> PlayerRef | None:
        if not self._player_resolved:
            java_ref = self._java.getPlayerRef()
            if java_ref is not None:
                self._player_ref = PlayerRef(java_ref)
            self._player_resolved = True
        return self._player_ref

    def get(self, name: str, default: Any = _SENTINEL) -> Any:
        if default is not _SENTINEL and not self._java.provided(name):
            return default
        return self._java.get(name)

    def is_provided(self, name: str) -> bool:
        return self._java.provided(name)

    def send_message(self, message: MessageLike) -> None:
        self.sender.send_message(message)
