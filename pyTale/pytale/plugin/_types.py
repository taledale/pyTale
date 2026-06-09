"""Type wrappers for Java objects from pyTale"""

from enum import IntEnum
from typing import Any


class ExecutionContext(IntEnum):
    """Context in which the plugin code is running"""

    GENERAL = 0
    SCHEDULER = 1
    WORLD = 2


class PluginIdentifier:
    """Wrapper for com.hypixel.hytale.common.plugin.PluginIdentifier"""

    def __init__(self, java_obj: Any):
        self._java = java_obj

    @property
    def group(self) -> str:
        """Plugin group (e.g., 'com.example')"""
        return self._java.getGroup()

    @property
    def name(self) -> str:
        """Plugin name (e.g., 'my-plugin')"""
        return self._java.getName()

    def __repr__(self) -> str:
        return f"PluginIdentifier({self.group}:{self.name})"


class PluginManifest:
    """Wrapper for com.hypixel.hytale.common.plugin.PluginManifest"""

    def __init__(self, java_obj: Any):
        self._java = java_obj

    @property
    def group(self) -> str:
        return self._java.getGroup()

    @property
    def name(self) -> str:
        return self._java.getName()

    @property
    def version(self) -> str:
        """Plugin version (e.g., '1.0.0')"""
        return str(self._java.getVersion())

    @property
    def description(self) -> str | None:
        return self._java.getDescription()

    @property
    def authors(self) -> list[str]:
        """List of author names"""
        java_authors = self._java.getAuthors()
        return [author.getName() for author in java_authors]

    @property
    def website(self) -> str | None:
        return self._java.getWebsite()

    def __repr__(self) -> str:
        return f"PluginManifest({self.name} v{self.version})"
