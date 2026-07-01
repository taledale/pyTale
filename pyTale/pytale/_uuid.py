"""Java <-> Python UUID conversion via the 128-bit integer value, avoiding a
string round-trip through toString()/fromString()"""

from typing import TYPE_CHECKING
from uuid import UUID

import java as _java

if TYPE_CHECKING:
    from java import JavaObject

_JavaUUID = _java.type("java.util.UUID")

_MASK_64 = (1 << 64) - 1
_SIGN_BIT_64 = 1 << 63
_WRAP_64 = 1 << 64


def java_uuid_to_python(java_uuid: "JavaObject") -> UUID:
    """Convert a java.util.UUID host object to a Python uuid.UUID."""
    msb = java_uuid.getMostSignificantBits() & _MASK_64
    lsb = java_uuid.getLeastSignificantBits() & _MASK_64
    return UUID(int=(msb << 64) | lsb)


def python_uuid_to_java(value: UUID) -> "JavaObject":
    """Convert a Python uuid.UUID to a java.util.UUID host object."""
    msb = (value.int >> 64) & _MASK_64
    lsb = value.int & _MASK_64
    if msb >= _SIGN_BIT_64:
        msb -= _WRAP_64
    if lsb >= _SIGN_BIT_64:
        lsb -= _WRAP_64
    return _JavaUUID(msb, lsb)
