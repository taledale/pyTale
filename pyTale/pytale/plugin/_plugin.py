"""Plugin information and initialization"""

from pathlib import Path
from typing import TYPE_CHECKING

from pytale.plugin._types import (
    ExecutionContext,
    PluginIdentifier,
    PluginManifest,
    PluginState,
)

if TYPE_CHECKING:
    from java import JavaObject

__identifier: PluginIdentifier | None = None
__manifest: PluginManifest | None = None
__data_directory: Path | None = None
__context: ExecutionContext | None = None
__plugin_ref: "JavaObject | None" = None
__world_context_manager: "JavaObject | None" = None


def _init_plugin(
    identifier: "JavaObject",
    manifest: "JavaObject",
    data_directory: "JavaObject",
    context: int,
    java_plugin: "JavaObject",
    world_context_manager: "JavaObject",
) -> None:
    """Called by Java during plugin context initialization"""
    global __identifier, __manifest, __data_directory, __context, __plugin_ref, __world_context_manager
    __identifier = PluginIdentifier(identifier)
    __manifest = PluginManifest(manifest)
    __data_directory = Path(str(data_directory))
    __context = ExecutionContext(context)
    __plugin_ref = java_plugin
    __world_context_manager = world_context_manager


def get_identifier() -> PluginIdentifier:
    """Get plugin identifier (group, name)"""
    if __identifier is None:
        raise RuntimeError("Plugin not initialized")
    return __identifier


def get_manifest() -> PluginManifest:
    """Get plugin manifest (metadata)"""
    if __manifest is None:
        raise RuntimeError("Plugin not initialized")
    return __manifest


def get_data_directory() -> Path:
    """Get plugin data directory Path"""
    if __data_directory is None:
        raise RuntimeError("Plugin not initialized")
    return __data_directory


def get_context() -> ExecutionContext:
    """Get current execution context (general or world)"""
    if __context is None:
        raise RuntimeError("Plugin not initialized")
    return __context


def get_state() -> PluginState:
    """Get current plugin lifecycle state, read live from the Java plugin object"""
    if __plugin_ref is None:
        raise RuntimeError("Plugin not initialized")
    return PluginState[str(__plugin_ref.getState().name())]


def get_world_context_manager() -> "JavaObject":
    """Get the Java WorldContextManager host object, used by World.execute() to
    dispatch a scheduled task into an arbitrary world's context."""
    if __world_context_manager is None:
        raise RuntimeError("Plugin not initialized")
    return __world_context_manager
