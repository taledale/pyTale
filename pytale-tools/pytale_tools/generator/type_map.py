from dataclasses import dataclass

from pytale_tools.exporter.models import Nullability

_PRIMITIVE_MAP: dict[str, str] = {
    "Z": "bool",
    "B": "int",
    "C": "str",
    "S": "int",
    "I": "int",
    "J": "int",
    "F": "float",
    "D": "float",
    "V": "None",
}

_REFERENCE_MAP: dict[str, str] = {
    "Ljava/lang/String;": "str",
    "Ljava/lang/Boolean;": "bool",
    "Ljava/lang/Byte;": "int",
    "Ljava/lang/Short;": "int",
    "Ljava/lang/Integer;": "int",
    "Ljava/lang/Long;": "int",
    "Ljava/lang/Float;": "float",
    "Ljava/lang/Double;": "float",
    "Ljava/lang/Void;": "None",
}

_WRAPPER_MAP: dict[str, tuple[str, str]] = {
    "Lcom/hypixel/hytale/server/core/universe/PlayerRef;": (
        "PlayerRef",
        "pytale.players",
    ),
    "Lcom/hypixel/hytale/server/core/universe/world/World;": (
        "World",
        "pytale.world",
    ),
    "Lcom/hypixel/hytale/server/core/Message;": (
        "Message",
        "pytale.message",
    ),
    "Lorg/joml/Vector3d;": ("Vector3", "pytale.math"),
    "Lorg/joml/Vector3dc;": ("Vector3", "pytale.math"),
    "Lorg/joml/Vector3f;": ("Vector3", "pytale.math"),
    "Lorg/joml/Vector3fc;": ("Vector3", "pytale.math"),
    "Lcom/hypixel/hytale/math/vector/Rotation3f;": ("Rotation3", "pytale.math"),
    "Lcom/hypixel/hytale/math/vector/Rotation3fc;": ("Rotation3", "pytale.math"),
}


@dataclass(frozen=True)
class ValueConverterInfo:
    """Describes a value type that isn't a pytale JavaWrapper (no `._java`
    attribute), so it can't use _WRAPPER_MAP's direct `WrapperClass(raw)` /
    `value._java` round-trip. Instead, reads/writes call dedicated conversion
    functions (e.g. pytale._uuid.java_uuid_to_python)."""

    python_class: str
    python_import: str
    from_java_func: str
    from_java_func_import: str
    to_java_func: str
    to_java_func_import: str


_VALUE_CONVERTER_MAP: dict[str, ValueConverterInfo] = {
    "Ljava/util/UUID;": ValueConverterInfo(
        python_class="UUID",
        python_import="uuid",
        from_java_func="java_uuid_to_python",
        from_java_func_import="pytale._uuid",
        to_java_func="python_uuid_to_java",
        to_java_func_import="pytale._uuid",
    ),
}


def map_descriptor(
    descriptor: str, nullability: Nullability = Nullability.UNSPECIFIED
) -> str:
    mapped = _PRIMITIVE_MAP.get(descriptor)
    if mapped is not None:
        return mapped

    mapped = _REFERENCE_MAP.get(descriptor)
    if mapped is not None:
        if nullability == Nullability.NULLABLE:
            return f"{mapped} | None"
        return mapped

    wrapper = _WRAPPER_MAP.get(descriptor)
    if wrapper is not None:
        cls_name = wrapper[0]
        if nullability == Nullability.NULLABLE:
            return f"{cls_name} | None"
        return cls_name

    converter = _VALUE_CONVERTER_MAP.get(descriptor)
    if converter is not None:
        if nullability == Nullability.NULLABLE:
            return f"{converter.python_class} | None"
        return converter.python_class

    if nullability == Nullability.NULLABLE:
        return '"JavaObject | None"'
    return '"JavaObject"'


def get_wrapper_info(descriptor: str) -> tuple[str, str] | None:
    return _WRAPPER_MAP.get(descriptor)


def get_value_converter_info(descriptor: str) -> ValueConverterInfo | None:
    return _VALUE_CONVERTER_MAP.get(descriptor)
