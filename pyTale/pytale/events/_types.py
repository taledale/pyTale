from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar

if TYPE_CHECKING:
    from java import JavaClass

TEvent = TypeVar("TEvent")
TResult = TypeVar("TResult")


class EventPriority(IntEnum):
    FIRST = -21844
    EARLY = -10922
    NORMAL = 0
    LATE = 10922
    LAST = 21844


class EventHandler(Generic[TEvent, TResult]):
    def __init__(
        self,
        java_class: "JavaClass",
        handler: Callable[[TEvent], TResult],
        *,
        key: Any = None,
        priority: EventPriority = EventPriority.NORMAL,
    ):
        self.java_class: "Final[JavaClass]" = java_class
        self.key: Final[Any] = key
        self.priority: Final[EventPriority] = priority
        self._handler = handler

    def __call__(self, event: TEvent) -> TResult:
        return self._handler(event)
