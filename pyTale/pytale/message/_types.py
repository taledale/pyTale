"""Message wrapper for styled, composed, and translatable chat messages"""

from typing import TYPE_CHECKING, TypeAlias

import java as _java

if TYPE_CHECKING:
    from java import JavaObject

from pytale._java_wrapper import JavaWrapper

_Message = _java.type("com.hypixel.hytale.server.core.Message")

MessageLike: TypeAlias = "str | Message"


class Message(JavaWrapper):
    """Wrapper for com.hypixel.hytale.server.core.Message.

    Provides a fluent API for building styled, composed, and translatable
    chat messages::

        Message.raw("Hello!").bold().color("#ff0000")

        Message.join(
            Message.raw("Click "),
            Message.raw("here").link("https://example.com").bold(),
        )

        Message.translation("welcome.greeting").param("player", name)
    """

    # --- factory methods ---

    @classmethod
    def raw(cls, text: str) -> "Message":
        return cls(_Message.raw(text))

    @classmethod
    def empty(cls) -> "Message":
        return cls(_Message.empty())

    @classmethod
    def translation(cls, message_id: str) -> "Message":
        return cls(_Message.translation(message_id))

    @classmethod
    def join(cls, *messages: "Message") -> "Message":
        result = cls(_Message.empty())
        for msg in messages:
            result._java.insert(msg._java)
        return result

    # --- styling ---

    def bold(self, value: bool = True) -> "Message":
        self._java.bold(value)
        return self

    def italic(self, value: bool = True) -> "Message":
        self._java.italic(value)
        return self

    def monospace(self, value: bool = True) -> "Message":
        self._java.monospace(value)
        return self

    def color(self, hex_color: str) -> "Message":
        self._java.color(hex_color)
        return self

    def link(self, url: str) -> "Message":
        self._java.link(url)
        return self

    # --- composition ---

    def insert(self, message: "Message | str") -> "Message":
        if isinstance(message, str):
            self._java.insert(_Message.raw(message))
        else:
            self._java.insert(message._java)
        return self

    def insert_all(self, *messages: "Message") -> "Message":
        for msg in messages:
            self._java.insert(msg._java)
        return self

    # --- i18n parameters ---

    def param(self, key: str, value: "str | bool | int | float | Message") -> "Message":
        if isinstance(value, Message):
            self._java.param(key, value._java)
        else:
            self._java.param(key, value)
        return self

    # --- operators ---

    def __add__(self, other: "Message | str") -> "Message":
        if isinstance(other, str):
            other = Message.raw(other)
        return Message.join(self, other)

    def __radd__(self, other: str) -> "Message":
        return Message.join(Message.raw(other), self)

    def __repr__(self) -> str:
        return f"Message({self._java})"
