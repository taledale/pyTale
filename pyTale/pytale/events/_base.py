from abc import ABC
from typing import TYPE_CHECKING, ClassVar

from pytale._java_wrapper import JavaWrapper

if TYPE_CHECKING:
    from java import JavaClass, JavaObject


class BaseEvent(JavaWrapper):
    _java_class: ClassVar["JavaClass"]


class Event(BaseEvent):
    pass


class AsyncEvent(BaseEvent):
    pass


class Cancellable(ABC):
    _java: "JavaObject"

    @property
    def is_cancelled(self) -> bool:
        return self._java.isCancelled()

    def cancel(self) -> None:
        self._java.setCancelled(True)


def get_java_class(event: type[BaseEvent]) -> "JavaClass":
    return event._java_class
