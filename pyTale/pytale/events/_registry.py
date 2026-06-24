import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast, overload

import java as _java
from pytale.events._base import AsyncEvent, Event
from pytale.events._types import (
    AsyncEventHandler,
    EventHandler,
    EventPriority,
    TEvent,
    TResult,
)
from pytale.plugin._plugin import get_context, get_state
from pytale.plugin._types import ExecutionContext, PluginState
from typing_extensions import deprecated

if TYPE_CHECKING:
    from java import JavaClass

_logger = logging.getLogger(__name__)

_handlers: list[EventHandler[Any, Any]] = []
_async_handlers: list[AsyncEventHandler[Any, Any]] = []
_tasks: set[asyncio.Task[None]] = set()

_IEvent = _java.type("com.hypixel.hytale.event.IEvent")
_IAsyncEvent = _java.type("com.hypixel.hytale.event.IAsyncEvent")
_RuntimeException = _java.type("java.lang.RuntimeException")

TWrapper = TypeVar("TWrapper", bound=Event)
TAsyncWrapper = TypeVar("TAsyncWrapper", bound=AsyncEvent)


class _JavaFuture(Protocol):
    """A ``java.util.concurrent.CompletableFuture`` as seen from Python."""

    def complete(self, value: Any) -> bool: ...
    def completeExceptionally(self, ex: Any) -> bool: ...


class _QueuedAsyncEvent(Protocol):
    """A ``dev.taledale.pytale.context.QueuedAsyncEvent`` record."""

    def index(self) -> int: ...
    def event(self) -> Any: ...
    def future(self) -> _JavaFuture: ...


class _AsyncEventQueue(Protocol):
    """The Java ``LinkedBlockingQueue<QueuedAsyncEvent>`` bridged from the host."""

    def take(self) -> _QueuedAsyncEvent: ...


async def _main(java_queue: _AsyncEventQueue) -> None:
    while True:
        # The blocking take() runs on a worker thread so it never stalls the event loop;
        # a poison pill (index < 0) is enqueued on shutdown to unblock it.
        queued = await asyncio.to_thread(java_queue.take)
        if queued.index() < 0:
            await asyncio.gather(*_tasks, return_exceptions=True)
            return
        task = asyncio.create_task(_invoke(queued))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def _invoke(queued: _QueuedAsyncEvent) -> None:
    handler = _async_handlers[queued.index()]
    raw_event = queued.event()
    wrapped = (
        handler.wrapper_class(raw_event)
        if handler.wrapper_class is not None
        else raw_event
    )
    try:
        await handler(wrapped)
        queued.future().complete(raw_event)
    except Exception as error:
        _logger.exception(
            "Error in async event handler %s: %s",
            handler._handler.__name__,
            repr(error),
        )
        queued.future().completeExceptionally(_RuntimeException(repr(error)))


def _start_loop(java_queue: _AsyncEventQueue) -> None:
    asyncio.run(_main(java_queue))


def _validate_java_class(java_class: "JavaClass") -> None:
    if not _java.is_symbol(java_class):
        raise TypeError(
            f"Expected a Java event class obtained via java.type(), "
            f"got {type(java_class).__name__}"
        )
    event_cls = getattr(java_class, "class")
    if not getattr(_IEvent, "class").isAssignableFrom(event_cls):
        raise TypeError(f"{event_cls.getName()} does not implement IEvent")


def _resolve_event_source(
    event_source: "JavaClass | type[Event] | type[AsyncEvent]",
) -> tuple["JavaClass", "type[Event] | type[AsyncEvent] | None", bool]:
    if isinstance(event_source, type):
        if issubclass(event_source, AsyncEvent):
            return event_source._java_class, event_source, True
        if issubclass(event_source, Event):
            return event_source._java_class, event_source, False
    _validate_java_class(event_source)
    is_async = getattr(_IAsyncEvent, "class").isAssignableFrom(
        getattr(event_source, "class")
    )
    return event_source, None, is_async


@overload
def on_event(
    event_class: type[TWrapper],
    /,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[[Callable[[TWrapper], TResult]], EventHandler[TWrapper, TResult]]: ...
@overload
def on_event(
    event_class: type[TAsyncWrapper],
    /,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[
    [Callable[[TAsyncWrapper], TResult]], AsyncEventHandler[TAsyncWrapper, TResult]
]: ...
@overload
def on_event(
    java_class: "JavaClass",
    /,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[[Callable[[TEvent], TResult]], EventHandler[TEvent, TResult]]: ...
def on_event(
    event_source: "JavaClass | type[Event] | type[AsyncEvent]",
    /,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[..., Any]:
    if get_context() == ExecutionContext.GENERAL:
        state = get_state()
        if state != PluginState.SETUP:
            raise RuntimeError(
                f"@on_event can only be used during plugin setup "
                f"(current state: {state.name})"
            )

    java_class, wrapper_class, is_async = _resolve_event_source(event_source)

    if is_async:
        return _async_decorator(
            java_class,
            cast(type[AsyncEvent] | None, wrapper_class),
            key=key,
            priority=priority,
        )
    return _sync_decorator(
        java_class, cast(type[Event] | None, wrapper_class), key=key, priority=priority
    )


@deprecated("Use on_event")
def on_async_event(
    event_source: "JavaClass",
    /,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[[Callable[[TEvent], TResult]], EventHandler[TEvent, TResult]]:
    return on_event(event_source, key=key, priority=priority)


def _sync_decorator(
    java_class: "JavaClass",
    wrapper_class: "type[Event] | None",
    *,
    key: Any,
    priority: EventPriority,
) -> Callable[..., EventHandler[Any, Any]]:
    def decorator(func: Callable[..., Any]) -> EventHandler[Any, Any]:
        if inspect.iscoroutinefunction(func):
            raise TypeError(
                f"async def {func.__name__} cannot be used with a synchronous event; "
                "the event class must extend AsyncEvent for async handlers"
            )
        _logger.debug(
            "Registering sync event handler %s for %s with priority %s and key %s",
            func.__name__,
            java_class,
            priority.name,
            key,
        )
        handler = EventHandler(
            java_class, func, key=key, priority=priority, wrapper_class=wrapper_class
        )
        _handlers.append(handler)
        return handler

    return decorator


def _async_decorator(
    java_class: "JavaClass",
    wrapper_class: "type[AsyncEvent] | None",
    *,
    key: Any,
    priority: EventPriority,
) -> Callable[..., AsyncEventHandler[Any, Any]]:
    if get_context() != ExecutionContext.GENERAL:

        def __no_op(func: Callable[..., Any]) -> AsyncEventHandler[Any, Any]:
            return AsyncEventHandler(
                java_class,
                func,
                key=key,
                priority=priority,
                wrapper_class=wrapper_class,
            )

        return __no_op

    def decorator(func: Callable[..., Any]) -> AsyncEventHandler[Any, Any]:
        actual = func
        if not inspect.iscoroutinefunction(func):

            async def _async_wrapper(event: Any) -> Any:
                return func(event)

            _async_wrapper.__name__ = func.__name__
            _async_wrapper.__qualname__ = func.__qualname__
            actual = _async_wrapper

        _logger.debug(
            "Registering async event handler %s for %s with priority %s and key %s",
            func.__name__,
            java_class,
            priority.name,
            key,
        )
        handler = AsyncEventHandler(
            java_class, actual, key=key, priority=priority, wrapper_class=wrapper_class
        )
        _async_handlers.append(handler)
        return handler

    return decorator


def _execute_handler(index: int, event: Any) -> None:
    handler = _handlers[index]
    try:
        wrapped = (
            handler.wrapper_class(event) if handler.wrapper_class is not None else event
        )
        handler(wrapped)
    except Exception as error:
        _logger.exception(
            "Error in event handler %s: %s", handler._handler.__name__, repr(error)
        )
