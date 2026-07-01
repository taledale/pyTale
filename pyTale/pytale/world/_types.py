"""Type wrappers, flags and errors for the world API"""

from enum import IntFlag
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
from uuid import UUID

import java as _java

if TYPE_CHECKING:
    from java import JavaObject

from pytale._java_wrapper import JavaWrapper
from pytale._uuid import java_uuid_to_python, python_uuid_to_java
from pytale.components import Component
from pytale.entities import EntityRef
from pytale.message import Message, MessageLike
from pytale.players import PlayerRef
from pytale.plugin._plugin import get_world_context_manager
from pytale.world._registry import Task
from pytale.world.errors import (
    ChunkNotLoadedError,
    NotInWorldThreadError,
    WorldNotAcceptingTasksError,
)

_Message = _java.type("com.hypixel.hytale.server.core.Message")
_ChunkUtil = _java.type("com.hypixel.hytale.math.util.ChunkUtil")
_EntityBridge = _java.type("dev.taledale.pytale.entity.EntityBridge")
_AddReason = _java.type("com.hypixel.hytale.component.AddReason")

_EXECUTE_PRIMITIVE_TYPES = (int, float, str, bool, type(None))

P = ParamSpec("P")
R = TypeVar("R")


def _prepare_execute_arg(arg: Any) -> Any:
    """Convert a single World.execute() argument to a cross-context-safe value.

    JavaWrapper instances unwrap to their raw Java host object (safe: Java
    host objects are Engine-scoped, not Context-scoped, unlike Python guest
    values — already relied on by Universe.get_world()'s existing
    cross-context return path). Raw Java host objects (java.is_object) pass
    through unchanged, for the same reason.
    """
    if isinstance(arg, JavaWrapper):
        return arg._java
    if _java.is_object(arg):
        return arg
    if isinstance(arg, _EXECUTE_PRIMITIVE_TYPES):
        return arg
    raise TypeError(
        "World.execute() arguments must be primitives (int, float, str, "
        "bool, None), a pytale wrapper type, or a raw Java object; got "
        f"{type(arg).__name__} for {arg!r}"
    )


class SetBlockSettings(IntFlag):
    """Bit flags for the ``settings`` argument of block operations,
    mirroring com.hypixel.hytale.server.core.universe.world.SetBlockSettings"""

    NONE = 0
    NO_NOTIFY = 1
    NO_UPDATE_STATE = 2
    NO_SEND_PARTICLES = 4
    NO_SET_FILLER = 8
    NO_BREAK_FILLER = 16
    PHYSICS = 32
    FORCE_CHANGED = 64
    NO_UPDATE_NEIGHBOR_CONNECTIONS = 128
    PERFORM_BLOCK_UPDATE = 256
    NO_UPDATE_HEIGHTMAP = 512
    NO_SEND_AUDIO = 1024
    NO_DROP_ITEMS = 2048


class WorldConfig(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.universe.world.WorldConfig"""

    @property
    def uuid(self) -> UUID:
        return java_uuid_to_python(self._java.getUuid())

    @property
    def seed(self) -> int:
        return self._java.getSeed()

    @property
    def display_name(self) -> str | None:
        return self._java.getDisplayName()

    @property
    def is_ticking(self) -> bool:
        return self._java.isTicking()

    @property
    def is_block_ticking(self) -> bool:
        return self._java.isBlockTicking()

    @property
    def is_pvp_enabled(self) -> bool:
        return self._java.isPvpEnabled()

    @property
    def is_fall_damage_enabled(self) -> bool:
        return self._java.isFallDamageEnabled()

    @property
    def is_game_time_paused(self) -> bool:
        return self._java.isGameTimePaused()

    @property
    def is_saving_players(self) -> bool:
        return self._java.isSavingPlayers()

    @property
    def can_save_chunks(self) -> bool:
        return self._java.canSaveChunks()

    @property
    def can_unload_chunks(self) -> bool:
        return self._java.canUnloadChunks()

    @property
    def forced_weather(self) -> str | None:
        return self._java.getForcedWeather()

    @property
    def default_permission_group(self) -> str:
        return self._java.getDefaultPermissionGroup()

    @property
    def game_mode(self) -> str:
        return str(self._java.getGameMode())

    def __repr__(self) -> str:
        return f"WorldConfig(uuid={self.uuid}, seed={self.seed})"


class World(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.universe.world.World.

    Most methods are safe from any context: read-only metadata, the
    ticking/paused setters, and send_message / is_chunk_loaded / get_entity (which
    self-dispatch onto the world thread). Only get_block, set_block, break_block,
    set_tps, entities, get_entity_by_network_id and spawn_entity must run on the
    world's own thread, because they read the chunk store or walk the entity store
    directly; those raise NotInWorldThreadError when called on a World obtained
    outside its WORLD context (e.g. one returned by the Universe in the general
    context).
    """

    def __init__(self, java_obj: "JavaObject") -> None:
        super().__init__(java_obj)
        self._config: WorldConfig | None = None

    def _require_thread(self, operation: str) -> None:
        """Raise NotInWorldThreadError unless we are on this world's thread."""
        if not self._java.isInThread():
            raise NotInWorldThreadError(self._java.getName(), operation)

    # --- read-only properties ---

    @property
    def name(self) -> str:
        return self._java.getName()

    @property
    def tick(self) -> int:
        return self._java.getTick()

    @property
    def is_alive(self) -> bool:
        return self._java.isAlive()

    @property
    def player_count(self) -> int:
        return self._java.getPlayerCount()

    @property
    def players(self) -> tuple[PlayerRef, ...]:
        """All players currently in this world."""
        return tuple(PlayerRef(player) for player in self._java.getPlayerRefs())

    @property
    def entities(self) -> tuple[EntityRef, ...]:
        """All entities currently in this world's entity store.

        Must run on this world's own tick thread; raises NotInWorldThreadError
        otherwise, since it walks the entity component store directly (see
        get_block for the same rationale).
        """
        self._require_thread("entities")
        store = self._java.getEntityStore().getStore()
        return tuple(
            EntityRef(ref, store, self.name, self._java)
            for ref in _EntityBridge.getAllRefs(self._java)
        )

    @property
    def daytime_duration_seconds(self) -> int:
        return self._java.getDaytimeDurationSeconds()

    @property
    def nighttime_duration_seconds(self) -> int:
        return self._java.getNighttimeDurationSeconds()

    @property
    def config(self) -> WorldConfig:
        if self._config is None:
            self._config = WorldConfig(self._java.getWorldConfig())
        return self._config

    # --- read/write properties ---

    @property
    def is_ticking(self) -> bool:
        return self._java.isTicking()

    @is_ticking.setter
    def is_ticking(self, value: bool) -> None:
        self._java.setTicking(value)

    @property
    def is_paused(self) -> bool:
        return self._java.isPaused()

    @is_paused.setter
    def is_paused(self, value: bool) -> None:
        self._java.setPaused(value)

    # --- block access ---

    def is_chunk_loaded(self, x: int, z: int) -> bool:
        """Return True if the chunk containing block column (x, z) is loaded and ticking.

        Callable from any context: the Java side self-dispatches when off the
        world thread. Off-thread it blocks until the world thread answers, so
        prefer calling it from the world's own context.
        """
        return (
            self._java.getChunkIfLoaded(_ChunkUtil.indexChunkFromBlock(x, z))
            is not None
        )

    def _chunk_at(self, x: int, y: int, z: int, force: bool) -> "JavaObject":
        """Return the chunk containing block (x, y, z).

        When ``force`` is True the chunk is loaded synchronously if it is not
        already in memory. When False, only an already-loaded chunk is used and
        ChunkNotLoadedError is raised otherwise (instead of a raw NPE).
        """
        index = _ChunkUtil.indexChunkFromBlock(x, z)
        if force:
            return self._java.getChunk(index)
        chunk = self._java.getChunkIfLoaded(index)
        if chunk is None:
            raise ChunkNotLoadedError(x, y, z)
        return chunk

    def get_block(self, x: int, y: int, z: int, force: bool = False) -> int:
        """Return the block type index at (x, y, z).

        When ``force`` is True the containing chunk is loaded if needed;
        otherwise ChunkNotLoadedError is raised if it is not already loaded.
        """
        self._require_thread("get_block")
        return self._chunk_at(x, y, z, force).getBlock(x, y, z)

    def set_block(
        self,
        x: int,
        y: int,
        z: int,
        block_type: str,
        settings: int = 0,
        force: bool = False,
    ) -> bool:
        """Set the block at (x, y, z) to the given block type key.

        ``block_type`` is an asset key (e.g. "hytale:stone"). ``settings`` is a
        bit mask from SetBlockSettings. Returns whether the block changed.
        When ``force`` is True the containing chunk is loaded if needed;
        otherwise ChunkNotLoadedError is raised if it is not already loaded.
        """
        self._require_thread("set_block")
        return self._chunk_at(x, y, z, force).setBlock(x, y, z, block_type, settings)

    def break_block(
        self, x: int, y: int, z: int, settings: int = 0, force: bool = False
    ) -> bool:
        """Break the block at (x, y, z), replacing it with air.

        ``settings`` is a bit mask from SetBlockSettings. Returns whether the
        block changed. When ``force`` is True the containing chunk is loaded if
        needed; otherwise ChunkNotLoadedError is raised if it is not loaded.
        """
        self._require_thread("break_block")
        return self._chunk_at(x, y, z, force).breakBlock(x, y, z, settings)

    # --- entity access ---

    def get_entity(self, uuid: UUID) -> EntityRef | None:
        """Return the entity with the given UUID, or None if not present.

        Safe to call from any context: the Java side self-dispatches when off the
        world thread (mirrors is_chunk_loaded).
        """
        ref = self._java.getEntityRef(python_uuid_to_java(uuid))
        if ref is None:
            return None
        return EntityRef(
            ref, self._java.getEntityStore().getStore(), self.name, self._java
        )

    def get_entity_by_network_id(self, network_id: int) -> EntityRef | None:
        """Return the entity with the given network id, or None if not present.

        Must run on this world's own tick thread; raises NotInWorldThreadError
        otherwise (EntityStore.getRefFromNetworkId has no self-dispatching
        passthrough on World, unlike get_entity/getEntityRef).
        """
        self._require_thread("get_entity_by_network_id")
        store = self._java.getEntityStore().getStore()
        ref = store.getRefFromNetworkId(network_id)
        if ref is None:
            return None
        return EntityRef(ref, store, self.name, self._java)

    def spawn_entity(self, *components: "Component") -> EntityRef:
        """Create a new entity in this world with the given initial components (zero
        or more instances of generated pytale.components classes).

        Must run on this world's own tick thread.
        """
        self._require_thread("spawn_entity")
        store = self._java.getEntityStore().getStore()
        holder = store.getRegistry().newHolder()
        for component in components:
            component_type = type(component)._java_class.getComponentType()
            holder.putComponent(component_type, component._java)
        ref = store.addEntity(holder, _AddReason.SPAWN)
        if ref is None:
            raise RuntimeError("entity was removed before spawn completed")
        return EntityRef(ref, store, self.name, self._java)

    # --- other methods ---

    def send_message(self, message: MessageLike) -> None:
        """Broadcast a message to all players in this world.

        Safe to call from any thread: the Java side self-enqueues the broadcast
        onto the world thread when called off it.
        """
        if isinstance(message, Message):
            self._java.sendMessage(message._java)
        else:
            self._java.sendMessage(_Message.raw(message))

    def set_tps(self, tps: int) -> None:
        """Set the world's target ticks per second."""
        self._require_thread("set_tps")
        self._java.setTps(tps)

    def execute(self, task: "Task[P, R]", *args: P.args, **kwargs: P.kwargs) -> None:
        """Schedule ``task`` to run on this world's tick thread, on a future tick.

        ``task`` must be a module-level function decorated with
        ``@pytale.world.task`` — a plain lambda/closure cannot be used, since
        GraalPy values cannot cross between Python contexts and this call may
        target a different world's context than the one calling it. Each
        positional/keyword argument must be a primitive (int, float, str,
        bool, None), a pytale wrapper instance (e.g. PlayerRef, World), or a
        raw Java host object, for the same reason. Wrapper instances are
        automatically unwrapped here and re-wrapped on arrival based on
        ``task``'s own parameter annotations.

        Callable from any context: the world's own context, another world's
        context, or the general/async context. Never runs inline, even when
        called from this world's own thread.
        """
        index = getattr(task, "_task_index", None)
        if index is None:
            raise TypeError(
                f"{getattr(task, '__name__', task)!r} is not a task; "
                "decorate it with @pytale.world.task"
            )
        prepared_args = tuple(_prepare_execute_arg(arg) for arg in args)
        prepared_kwargs = {k: _prepare_execute_arg(v) for k, v in kwargs.items()}
        status = get_world_context_manager().executeTask(
            self._java, index, prepared_args, prepared_kwargs
        )
        if status == "not_accepting":
            raise WorldNotAcceptingTasksError(self.name)
        # "no_context" is a silent no-op (world's context isn't up yet or was
        # torn down); "ok" means the task was successfully enqueued.

    def __repr__(self) -> str:
        return f"World({self.name})"
