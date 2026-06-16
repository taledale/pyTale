import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

import java as _java
from pytale.events._types import AsyncEventHandler, EventPriority, TEvent, TResult
from pytale.plugin._plugin import get_context, get_state
from pytale.plugin._types import ExecutionContext, PluginState

if TYPE_CHECKING:
    from java import JavaClass

_IEvent = _java.type("com.hypixel.hytale.event.IEvent")
_IAsyncEvent = _java.type("com.hypixel.hytale.event.IAsyncEvent")
_RuntimeException = _java.type("java.lang.RuntimeException")

_logger = logging.getLogger(__name__)

_async_handlers: list[AsyncEventHandler[Any, Any]] = []
_tasks: set[asyncio.Task[None]] = set()


# ── Protocols for Java objects bridged from the host ─────────────────────────


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


# ── Event loop ────────────────────────────────────────────────────────────────


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
    event = queued.event()
    try:
        await handler(event)
        queued.future().complete(event)
    except Exception as error:
        _logger.exception(
            "Error in async event handler %s: %s",
            handler._handler.__name__,
            repr(error),
        )
        queued.future().completeExceptionally(_RuntimeException(repr(error)))


def _start_loop(java_queue: _AsyncEventQueue) -> None:
    asyncio.run(_main(java_queue))


# ── Registration ──────────────────────────────────────────────────────────────


def _check_event_class(java_class: "JavaClass") -> None:
    if not _java.is_symbol(java_class):
        raise TypeError(
            f"Expected a Java event class obtained via java.type(), got {type(java_class).__name__}"
        )
    event_cls = getattr(java_class, "class")
    if not getattr(_IAsyncEvent, "class").isAssignableFrom(event_cls):
        if getattr(_IEvent, "class").isAssignableFrom(event_cls):
            raise TypeError(
                f"{event_cls.getName()} is a synchronous IEvent; use @on_event instead"
            )
        raise TypeError(f"{event_cls.getName()} does not implement IAsyncEvent")


def on_async_event(
    java_class: "JavaClass",
    *,
    key: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable[
    [Callable[[TEvent], Awaitable[TResult]]], AsyncEventHandler[TEvent, TResult]
]:
    if get_context() != ExecutionContext.GENERAL:

        def __no_op(
            func: Callable[[TEvent], Awaitable[TResult]],
        ) -> AsyncEventHandler[TEvent, TResult]:
            return AsyncEventHandler(java_class, func, key=key, priority=priority)

        return __no_op

    state = get_state()
    if state != PluginState.SETUP:
        raise RuntimeError(
            f"@on_async_event can only be used during plugin setup "
            f"(current state: {state.name})"
        )

    _check_event_class(java_class)

    def decorator(
        func: Callable[[TEvent], Awaitable[TResult]],
    ) -> AsyncEventHandler[TEvent, TResult]:
        _logger.debug(
            "Registering async event handler %s for %s with priority %s and key %s",
            func.__name__,
            java_class,
            priority.name,
            key,
        )
        handler = AsyncEventHandler(java_class, func, key=key, priority=priority)
        _async_handlers.append(handler)
        return handler

    return decorator
