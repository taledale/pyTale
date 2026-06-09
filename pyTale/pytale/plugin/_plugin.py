"""Plugin information and initialization"""

from pathlib import Path
from typing import Any

from pytale.plugin._types import ExecutionContext, PluginIdentifier, PluginManifest

__identifier: PluginIdentifier | None = None
__manifest: PluginManifest | None = None
__data_directory: Path | None = None
__context: ExecutionContext | None = None


def _init_plugin(
    identifier: Any, manifest: Any, data_directory: Any, context: int
) -> None:
    """Called by Java during plugin context initialization"""
    global __identifier, __manifest, __data_directory, __context
    __identifier = PluginIdentifier(identifier)
    __manifest = PluginManifest(manifest)
    __data_directory = Path(str(data_directory))
    __context = ExecutionContext(context)


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
    """Get current execution context (general, scheduler, or world)"""
    if __context is None:
        raise RuntimeError("Plugin not initialized")
    return __context
