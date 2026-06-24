from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar

if TYPE_CHECKING:
    from java import JavaClass
    from pytale.events._base import BaseEvent

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
        wrapper_class: "type[BaseEvent] | None" = None,
    ):
        self.java_class: Final["JavaClass"] = java_class
        self.key: Final[Any] = key
        self.priority: Final[EventPriority] = priority
        self.wrapper_class: Final["type[BaseEvent] | None"] = wrapper_class
        self._handler: Callable[[TEvent], TResult] = handler

    def __call__(self, event: TEvent) -> TResult:
        return self._handler(event)


class AsyncEventHandler(EventHandler[TEvent, Awaitable[TResult]]):
    """Handler for IAsyncEvent events. Requires an async callable."""

    def __init__(
        self,
        java_class: "JavaClass",
        handler: Callable[[TEvent], Awaitable[TResult]],
        *,
        key: Any = None,
        priority: EventPriority = EventPriority.NORMAL,
        wrapper_class: "type[BaseEvent] | None" = None,
    ):
        super().__init__(
            java_class, handler, key=key, priority=priority, wrapper_class=wrapper_class
        )
