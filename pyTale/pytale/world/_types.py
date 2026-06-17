"""Type wrappers, flags and errors for the world API"""

from enum import IntFlag
from typing import TYPE_CHECKING

import java as _java

if TYPE_CHECKING:
    from java import JavaObject

from pytale.world.errors import ChunkNotLoadedError

_Message = _java.type("com.hypixel.hytale.server.core.Message")
_ChunkUtil = _java.type("com.hypixel.hytale.math.util.ChunkUtil")


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


class WorldConfig:
    """Wrapper for com.hypixel.hytale.server.core.universe.world.WorldConfig"""

    def __init__(self, java_obj: "JavaObject") -> None:
        self._java = java_obj

    @property
    def uuid(self) -> str:
        return str(self._java.getUuid())

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


class World:
    """Wrapper for com.hypixel.hytale.server.core.universe.world.World"""

    def __init__(self, java_obj: "JavaObject") -> None:
        self._java = java_obj
        self._config: WorldConfig | None = None

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
        """Return True if the chunk containing block column (x, z) is loaded and ticking."""
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
        return self._chunk_at(x, y, z, force).setBlock(x, y, z, block_type, settings)

    def break_block(
        self, x: int, y: int, z: int, settings: int = 0, force: bool = False
    ) -> bool:
        """Break the block at (x, y, z), replacing it with air.

        ``settings`` is a bit mask from SetBlockSettings. Returns whether the
        block changed. When ``force`` is True the containing chunk is loaded if
        needed; otherwise ChunkNotLoadedError is raised if it is not loaded.
        """
        return self._chunk_at(x, y, z, force).breakBlock(x, y, z, settings)

    # --- other methods ---

    def send_message(self, message: str) -> None:
        """Broadcast a raw text message to all players in this world."""
        self._java.sendMessage(_Message.raw(message))

    def set_tps(self, tps: int) -> None:
        """Set the world's target ticks per second."""
        self._java.setTps(tps)

    def __repr__(self) -> str:
        return f"World({self.name})"
