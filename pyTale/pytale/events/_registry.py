import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import java as _java
from pytale.events._types import EventHandler, EventPriority, TEvent, TResult

if TYPE_CHECKING:
    from java import JavaClass

_logger = logging.getLogger(__name__)

_handlers: list[EventHandler[Any, Any]] = []

_IEvent = _java.type("com.hypixel.hytale.event.IEvent")


def _check_event_class(java_class: "JavaClass") -> None:
    if not _java.is_symbol(java_class):
        raise TypeError(
            f"Expected a Java event class obtained via java.type(), got {type(java_class).__name__}"
        )
    event_cls = getattr(java_class, "class")
    if not getattr(_IEvent, "class").isAssignableFrom(event_cls):
        raise TypeError(
            f"{event_cls.getName()} does not implement IEvent. "
            "Note: IAsyncEvent is not currently supported."
        )


def on_event(
    java_class: "JavaClass",
    *,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[[Callable[[TEvent], TResult]], EventHandler[TEvent, TResult]]:
    _check_event_class(java_class)

    def decorator(func: Callable[[TEvent], TResult]) -> EventHandler[TEvent, TResult]:
        _logger.debug(
            "Registering event handler %s for %s with priority %s and key %s",
            func.__name__,
            java_class,
            priority.name,
            key,
        )
        handler = EventHandler(java_class, func, key=key, priority=priority)
        _handlers.append(handler)
        return handler

    return decorator


def _execute_handler(index: int, event: Any) -> None:
    handler = _handlers[index]
    try:
        handler(event)
    except Exception as error:
        _logger.exception(
            "Error in event handler %s: %s", handler._handler.__name__, repr(error)
        )
