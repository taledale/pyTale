"""Type wrappers for the server-wide permissions system"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Set
from typing import TYPE_CHECKING, Any, ClassVar, NewType, Protocol, final
from uuid import UUID

import java as _java

if TYPE_CHECKING:
    from java import JavaObject

from pytale._java_wrapper import JavaWrapper
from pytale.players import PlayerRef

Permission = NewType("Permission", str)
GroupName = NewType("GroupName", str)


_PermissionsModule = _java.type(
    "com.hypixel.hytale.server.core.permissions.PermissionsModule"
)
_UUID = _java.type("java.util.UUID")
_HashSet = _java.type("java.util.HashSet")
_HashMap = _java.type("java.util.HashMap")


class _JavaCollection(Protocol):
    """Protocol for GraalPy Java collections that are iterable at runtime."""

    def __iter__(self) -> Iterator[Any]: ...
    def __len__(self) -> int: ...


def _to_java_set(strings: Iterable[str]) -> "JavaObject":
    java_set = _HashSet()
    for s in strings:
        java_set.add(s)
    return java_set


def _resolve_uuid(player: "PlayerRef | UUID") -> "JavaObject":
    if isinstance(player, PlayerRef):
        return player._java.getUuid()
    return _UUID.fromString(str(player))


def _to_python_uuid(java_uuid: "JavaObject") -> UUID:
    return UUID(str(java_uuid))


class PermissionProvider(ABC):
    """Base class for custom permission providers.

    Subclass this and register via ``get_manager().add_provider(instance)``
    to supply permissions from a custom backend (database, remote service, etc.).
    """

    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def get_user_permissions(self, uuid: UUID) -> Set[Permission]: ...

    @abstractmethod
    def add_user_permissions(
        self, uuid: UUID, permissions: Set[Permission]
    ) -> None: ...

    @abstractmethod
    def remove_user_permissions(
        self, uuid: UUID, permissions: Set[Permission]
    ) -> None: ...

    @abstractmethod
    def get_group_permissions(self, group: GroupName) -> Set[Permission]: ...

    @abstractmethod
    def get_effective_group_permissions(self, group: GroupName) -> Set[Permission]: ...

    @abstractmethod
    def add_group_permissions(
        self, group: GroupName, permissions: Set[Permission]
    ) -> None: ...

    @abstractmethod
    def remove_group_permissions(
        self, group: GroupName, permissions: Set[Permission]
    ) -> None: ...

    @abstractmethod
    def get_groups_for_user(self, uuid: UUID) -> Set[GroupName]: ...

    @abstractmethod
    def add_user_to_group(self, uuid: UUID, group: GroupName) -> None: ...

    @abstractmethod
    def remove_user_from_group(self, uuid: UUID, group: GroupName) -> None: ...

    @abstractmethod
    def set_user_group(self, uuid: UUID, group: GroupName) -> None: ...

    @abstractmethod
    def get_group_parent(self, group: GroupName) -> GroupName | None: ...

    @abstractmethod
    def get_all_registered_groups(self) -> Set[GroupName]: ...


class _ProviderBridge:
    """Adapts a Python PermissionProvider to the Java PermissionProvider interface.

    Exposes camelCase methods that GraalPy maps to the Java interface.
    Handles UUID and Set conversion in both directions.
    """

    def __init__(self, provider: PermissionProvider) -> None:
        self._provider = provider

    def getName(self) -> str:
        return self._provider.get_name()

    def getUserPermissions(self, uuid: "JavaObject") -> "JavaObject":
        return _to_java_set(self._provider.get_user_permissions(_to_python_uuid(uuid)))

    def addUserPermissions(
        self, uuid: "JavaObject", permissions: _JavaCollection
    ) -> None:
        self._provider.add_user_permissions(
            _to_python_uuid(uuid),
            frozenset(Permission(str(s)) for s in permissions),
        )

    def removeUserPermissions(
        self, uuid: "JavaObject", permissions: _JavaCollection
    ) -> None:
        self._provider.remove_user_permissions(
            _to_python_uuid(uuid),
            frozenset(Permission(str(s)) for s in permissions),
        )

    def getGroupPermissions(self, group: str) -> "JavaObject":
        return _to_java_set(self._provider.get_group_permissions(GroupName(group)))

    def getEffectiveGroupPermissions(self, group: str) -> "JavaObject":
        return _to_java_set(
            self._provider.get_effective_group_permissions(GroupName(group))
        )

    def addGroupPermissions(self, group: str, permissions: _JavaCollection) -> None:
        self._provider.add_group_permissions(
            GroupName(group),
            frozenset(Permission(str(s)) for s in permissions),
        )

    def removeGroupPermissions(self, group: str, permissions: _JavaCollection) -> None:
        self._provider.remove_group_permissions(
            GroupName(group),
            frozenset(Permission(str(s)) for s in permissions),
        )

    def getGroupsForUser(self, uuid: "JavaObject") -> "JavaObject":
        return _to_java_set(self._provider.get_groups_for_user(_to_python_uuid(uuid)))

    def addUserToGroup(self, uuid: "JavaObject", group: str) -> None:
        self._provider.add_user_to_group(_to_python_uuid(uuid), GroupName(group))

    def removeUserFromGroup(self, uuid: "JavaObject", group: str) -> None:
        self._provider.remove_user_from_group(_to_python_uuid(uuid), GroupName(group))

    def setUserGroup(self, uuid: "JavaObject", group: str) -> None:
        self._provider.set_user_group(_to_python_uuid(uuid), GroupName(group))

    def getGroupParent(self, group: str) -> str | None:
        return self._provider.get_group_parent(GroupName(group))

    def getAllRegisteredGroups(self) -> "JavaObject":
        return _to_java_set(self._provider.get_all_registered_groups())


@final
class PermissionsManager(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.permissions.PermissionsModule.

    The permissions module is a process-wide singleton that manages permission
    registration, user/group permissions, and permission providers. Obtain via
    ``PermissionsManager()`` or ``get_manager()``.
    """

    _instance: ClassVar["PermissionsManager | None"] = None
    _bridges: dict[PermissionProvider, _ProviderBridge]

    def __new__(cls) -> "PermissionsManager":
        if cls._instance is not None:
            return cls._instance
        self = super().__new__(cls)
        self._java = _PermissionsModule.get()
        self._bridges = {}
        cls._instance = self
        return self

    def __init__(self) -> None:
        pass  # _java/_bridges are already set in __new__

    def register_permission(self, permission: Permission, *groups: GroupName) -> None:
        """Register a permission node, optionally assigning it to groups."""
        if groups:
            _PermissionsModule.registerPermission(permission, *groups)
        else:
            _PermissionsModule.registerPermission(permission)

    def get_registered_permissions(
        self,
    ) -> dict[Permission, frozenset[GroupName]]:
        """Return all registered permissions mapped to their assigned groups."""
        java_map = _PermissionsModule.getRegisteredPermissions()
        result: dict[Permission, frozenset[GroupName]] = {}
        for entry in java_map.entrySet():
            result[Permission(str(entry.getKey()))] = frozenset(
                GroupName(str(s)) for s in entry.getValue()
            )
        return result

    def has_permission(
        self,
        player: "PlayerRef | UUID",
        permission: Permission,
        default: bool | None = None,
    ) -> bool:
        """Check whether a player has a specific permission.

        When ``default`` is given it is used for permissions that are not
        explicitly set; otherwise the server's own default applies.
        """
        uuid = _resolve_uuid(player)
        if default is None:
            return self._java.hasPermission(uuid, permission)
        return self._java.hasPermission(uuid, permission, default)

    def add_user_permissions(
        self, player: "PlayerRef | UUID", permissions: set[Permission]
    ) -> None:
        """Grant permissions to a player."""
        self._java.addUserPermission(_resolve_uuid(player), _to_java_set(permissions))

    def remove_user_permissions(
        self, player: "PlayerRef | UUID", permissions: set[Permission]
    ) -> None:
        """Revoke permissions from a player."""
        self._java.removeUserPermission(
            _resolve_uuid(player), _to_java_set(permissions)
        )

    def get_groups(self, player: "PlayerRef | UUID") -> frozenset[GroupName]:
        """Return all groups the player belongs to."""
        return frozenset(
            GroupName(str(g))
            for g in self._java.getGroupsForUser(_resolve_uuid(player))
        )

    def set_group(self, player: "PlayerRef | UUID", group: GroupName) -> None:
        """Set the player's group, replacing any existing group assignments."""
        self._java.setUserGroup(_resolve_uuid(player), group)

    def add_to_group(self, player: "PlayerRef | UUID", group: GroupName) -> None:
        """Add a player to a permission group."""
        self._java.addUserToGroup(_resolve_uuid(player), group)

    def remove_from_group(self, player: "PlayerRef | UUID", group: GroupName) -> None:
        """Remove a player from a permission group."""
        self._java.removeUserFromGroup(_resolve_uuid(player), group)

    def add_group_permissions(
        self, group: GroupName, permissions: set[Permission]
    ) -> None:
        """Grant permissions to a group."""
        self._java.addGroupPermission(group, _to_java_set(permissions))

    def remove_group_permissions(
        self, group: GroupName, permissions: set[Permission]
    ) -> None:
        """Revoke permissions from a group."""
        self._java.removeGroupPermission(group, _to_java_set(permissions))

    @property
    def all_groups(self) -> frozenset[GroupName]:
        """All registered permission group names."""
        return frozenset(GroupName(str(g)) for g in self._java.getAllRegisteredGroups())

    @property
    def virtual_groups(self) -> dict[GroupName, frozenset[Permission]]:
        """Current virtual group mappings."""
        java_map = self._java.getVirtualGroups()
        result: dict[GroupName, frozenset[Permission]] = {}
        for entry in java_map.entrySet():
            result[GroupName(str(entry.getKey()))] = frozenset(
                Permission(str(s)) for s in entry.getValue()
            )
        return result

    @virtual_groups.setter
    def virtual_groups(self, groups: dict[GroupName, set[Permission]]) -> None:
        java_map = _HashMap()
        for key, values in groups.items():
            java_map.put(key, _to_java_set(values))
        self._java.setVirtualGroups(java_map)

    @property
    def providers(self) -> list["JavaObject"]:
        """All registered permission providers (as raw Java objects)."""
        return list(self._java.getProviders())

    @property
    def first_provider(self) -> "JavaObject":
        """The first (highest priority) permission provider."""
        return self._java.getFirstPermissionProvider()

    @property
    def are_providers_tampered(self) -> bool:
        """Whether the provider list differs from the default configuration."""
        return self._java.areProvidersTampered()

    def add_provider(self, provider: PermissionProvider) -> None:
        """Register a custom permission provider."""
        bridge = _ProviderBridge(provider)
        self._bridges[provider] = bridge
        self._java.addProvider(bridge)

    def remove_provider(self, provider: PermissionProvider) -> None:
        """Unregister a previously added permission provider."""
        bridge = self._bridges.pop(provider, None)
        if bridge is not None:
            self._java.removeProvider(bridge)

    def reload(self) -> None:
        """Reload permission data from the standard provider."""
        self._java.reload()

    def __repr__(self) -> str:
        return (
            f"PermissionsManager(groups={len(self.all_groups)},"
            f" providers={len(self.providers)})"
        )
