import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import java as _java
from pytale.events._types import EventHandler, EventPriority, TEvent, TResult
from pytale.plugin._plugin import get_context, get_state
from pytale.plugin._types import ExecutionContext, PluginState

if TYPE_CHECKING:
    from java import JavaClass

_logger = logging.getLogger(__name__)

_handlers: list[EventHandler[Any, Any]] = []

_IEvent = _java.type("com.hypixel.hytale.event.IEvent")
_IAsyncEvent = _java.type("com.hypixel.hytale.event.IAsyncEvent")


def _check_event_class(java_class: "JavaClass") -> None:
    if not _java.is_symbol(java_class):
        raise TypeError(
            f"Expected a Java event class obtained via java.type(), got {type(java_class).__name__}"
        )
    event_cls = getattr(java_class, "class")
    if getattr(_IAsyncEvent, "class").isAssignableFrom(event_cls):
        raise TypeError(
            f"{event_cls.getName()} is an IAsyncEvent; use @on_async_event instead"
        )
    if not getattr(_IEvent, "class").isAssignableFrom(event_cls):
        raise TypeError(f"{event_cls.getName()} does not implement IEvent")


def on_event(
    java_class: "JavaClass",
    *,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[[Callable[[TEvent], TResult]], EventHandler[TEvent, TResult]]:
    if get_context() == ExecutionContext.GENERAL:
        state = get_state()
        if state != PluginState.SETUP:
            raise RuntimeError(
                f"@on_event can only be used during plugin setup "
                f"(current state: {state.name})"
            )

    _check_event_class(java_class)

    def decorator(func: Callable[[TEvent], TResult]) -> EventHandler[TEvent, TResult]:
        if inspect.iscoroutinefunction(func):
            raise TypeError(
                f"async def {func.__name__} cannot be used with @on_event; "
                "use @on_async_event for IAsyncEvent handlers"
            )
        _logger.debug(
            "Registering sync event handler %s for %s with priority %s and key %s",
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
