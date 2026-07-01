"""Scheduled-task registry for World.execute()"""

import inspect
import logging
import types
from collections.abc import Callable
from typing import Any, Generic, ParamSpec, TypeVar, Union, get_args, get_origin

from pytale._java_wrapper import JavaWrapper

_logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class Task(Generic[P, R]):
    """A module-level function registered via ``@pytale.world.task``.

    Wraps the original function, preserving its call signature for static
    checking (see ``World.execute``) while remaining directly callable so
    existing call sites (e.g. tests) that invoke the decorated function
    normally keep working unchanged.
    """

    def __init__(self, func: Callable[P, R], index: int) -> None:
        self._func = func
        self._task_index = index
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self._func(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Task({self._func.__name__})"


_tasks: list[Task[Any, Any]] = []


def task(func: Callable[P, R]) -> Task[P, R]:
    """Register a module-level function as schedulable via World.execute().

    Must decorate a plain top-level function (not a lambda/closure/method):
    every WorldPythonContext imports the same plugin module in the same
    order, so the registration index is a stable key across contexts. Java
    passes only this index (plus args/kwargs) across the context boundary,
    never the function object itself, since GraalPy values cannot cross
    between contexts.
    """
    index = len(_tasks)
    wrapped = Task(func, index)
    _tasks.append(wrapped)
    _logger.debug("Registered world task %s with index %d", func.__name__, index)
    return wrapped


def _unwrap_optional_wrapper_annotation(annotation: Any) -> "type[JavaWrapper] | None":
    """If ``annotation`` is a JavaWrapper subclass, or a 2-member union of one
    with ``None`` (``SomeWrapper | None`` / ``Optional[SomeWrapper]``), return
    that subclass; otherwise None (including for the TYPE_CHECKING-only
    string annotation ``"JavaObject"``, which is never rewrapped)."""
    if isinstance(annotation, type) and issubclass(annotation, JavaWrapper):
        return annotation
    if get_origin(annotation) in (types.UnionType, Union):
        members = [a for a in get_args(annotation) if a is not type(None)]
        if (
            len(members) == 1
            and isinstance(members[0], type)
            and issubclass(members[0], JavaWrapper)
        ):
            return members[0]
    return None


def _rewrap_java_args(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Reconstruct JavaWrapper-typed parameters from the raw Java host objects
    that crossed the context boundary, using ``func``'s own signature
    (captured in the defining context, where wrapper-typed annotations are
    real classes, not strings). Extra positional args and unknown kwargs
    (e.g. absorbed by *args/**kwargs in the task itself) pass through raw."""
    try:
        params = list(inspect.signature(func).parameters.values())
    except (TypeError, ValueError):
        return args, kwargs

    new_args = list(args)
    for i, value in enumerate(new_args):
        if i >= len(params) or params[i].kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            break
        wrapper_cls = _unwrap_optional_wrapper_annotation(params[i].annotation)
        if wrapper_cls is not None and not isinstance(value, wrapper_cls):
            new_args[i] = wrapper_cls(value)

    param_by_name = {p.name: p for p in params}
    new_kwargs = dict(kwargs)
    for name, value in kwargs.items():
        param = param_by_name.get(name)
        wrapper_cls = (
            _unwrap_optional_wrapper_annotation(param.annotation) if param else None
        )
        if wrapper_cls is not None and not isinstance(value, wrapper_cls):
            new_kwargs[name] = wrapper_cls(value)

    return tuple(new_args), new_kwargs


def _execute_task(index: int, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Called by Java (WorldPythonContext.invokeScheduledTask) on the target
    world's own thread, inside that world's own context."""
    task_obj = _tasks[index]
    try:
        rewrapped_args, rewrapped_kwargs = _rewrap_java_args(
            task_obj._func, args, kwargs
        )
        task_obj._func(*rewrapped_args, **rewrapped_kwargs)
    except Exception as error:
        _logger.exception(
            "Error in scheduled task %s: %s", task_obj._func.__name__, repr(error)
        )
