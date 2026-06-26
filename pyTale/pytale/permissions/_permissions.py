"""Access to the server-wide permissions module singleton"""

from pytale.permissions._types import PermissionsManager


def get_manager() -> PermissionsManager:
    """Get the server PermissionsManager.

    The permissions module is a process-wide singleton resolved on first use
    and cached, available in any execution context.
    """
    return PermissionsManager()
