"""Shared base class for pyTale's Java-object wrapper types"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from java import JavaObject


class JavaWrapper(ABC):
    """Base for pyTale types that wrap a single Java host object as ``self._java``.

    Subclasses may override ``__init__`` to cache extra lazy state, but must
    call ``super().__init__(java_obj)`` first so ``self._java`` is set.
    """

    def __init__(self, java_obj: "JavaObject") -> None:
        self._java = java_obj

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._java})"
