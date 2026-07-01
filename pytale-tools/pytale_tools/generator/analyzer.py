from dataclasses import dataclass

from pytale_tools.exporter.models import ClassMeta, MethodMeta, Nullability
from pytale_tools.generator.naming import (
    extract_getter_stem,
    extract_setter_stem,
    java_getter_to_python_name,
)
from pytale_tools.generator.type_map import (
    get_value_converter_info,
    get_wrapper_info,
    map_descriptor,
)


@dataclass(frozen=True)
class PropertySpec:
    python_name: str
    getter_java_name: str
    setter_java_name: str | None
    return_type: str
    setter_param_type: str | None
    nullability: Nullability
    wrapper_class: str | None = None
    wrapper_import: str | None = None
    setter_wrapper_class: str | None = None
    value_converter_class: str | None = None
    value_converter_import: str | None = None
    from_java_func: str | None = None
    from_java_func_import: str | None = None
    setter_to_java_func: str | None = None
    setter_to_java_func_import: str | None = None
    is_deprecated: bool = False


_SKIP_METHODS = frozenset(
    {
        "<init>",
        "<clinit>",
        "toString",
        "hashCode",
        "equals",
        "getClass",
        "notify",
        "notifyAll",
        "wait",
    }
)

_CANCELLABLE_METHODS = frozenset({"isCancelled", "setCancelled"})


def _is_candidate(method: MethodMeta) -> bool:
    if (
        not method.is_public
        or method.is_static
        or method.is_bridge
        or method.is_synthetic
    ):
        return False
    return method.name not in _SKIP_METHODS


def _is_getter(method: MethodMeta) -> bool:
    if method.param_type_descriptors or method.return_type_descriptor == "V":
        return False
    return extract_getter_stem(method.name) is not None


def _is_setter(method: MethodMeta) -> bool:
    if len(method.param_type_descriptors) != 1 or method.return_type_descriptor != "V":
        return False
    return extract_setter_stem(method.name) is not None


def analyze_properties(cls: ClassMeta) -> None:
    skip = _CANCELLABLE_METHODS if cls.is_cancellable else frozenset()

    candidates = [m for m in cls.methods if _is_candidate(m) and m.name not in skip]

    getters: dict[str, MethodMeta] = {}
    setters: dict[str, MethodMeta] = {}

    for m in candidates:
        if _is_getter(m):
            stem = extract_getter_stem(m.name)
            if stem is not None:
                getters[stem] = m
        elif _is_setter(m):
            stem = extract_setter_stem(m.name)
            if stem is not None:
                setters[stem] = m

    properties: list[PropertySpec] = []
    for stem, getter in getters.items():
        setter = setters.get(stem)
        python_name = java_getter_to_python_name(getter.name)
        return_type = map_descriptor(getter.return_type_descriptor, getter.nullability)

        wrapper_info = get_wrapper_info(getter.return_type_descriptor)
        wrapper_class = wrapper_info[0] if wrapper_info else None
        wrapper_import = wrapper_info[1] if wrapper_info else None

        value_converter_class: str | None = None
        value_converter_import: str | None = None
        from_java_func: str | None = None
        from_java_func_import: str | None = None
        if wrapper_info is None:
            converter_info = get_value_converter_info(getter.return_type_descriptor)
            if converter_info is not None:
                value_converter_class = converter_info.python_class
                value_converter_import = converter_info.python_import
                from_java_func = converter_info.from_java_func
                from_java_func_import = converter_info.from_java_func_import

        setter_param_type: str | None = None
        setter_java_name: str | None = None
        setter_wrapper_class: str | None = None
        setter_to_java_func: str | None = None
        setter_to_java_func_import: str | None = None
        if setter is not None:
            setter_java_name = setter.name
            setter_param_type = map_descriptor(
                setter.param_type_descriptors[0], Nullability.UNSPECIFIED
            )
            setter_wrapper_info = get_wrapper_info(setter.param_type_descriptors[0])
            if setter_wrapper_info:
                setter_wrapper_class = setter_wrapper_info[0]
            else:
                setter_converter_info = get_value_converter_info(
                    setter.param_type_descriptors[0]
                )
                if setter_converter_info is not None:
                    setter_to_java_func = setter_converter_info.to_java_func
                    setter_to_java_func_import = (
                        setter_converter_info.to_java_func_import
                    )

        properties.append(
            PropertySpec(
                python_name=python_name,
                getter_java_name=getter.name,
                setter_java_name=setter_java_name,
                return_type=return_type,
                setter_param_type=setter_param_type,
                nullability=getter.nullability,
                wrapper_class=wrapper_class,
                wrapper_import=wrapper_import,
                setter_wrapper_class=setter_wrapper_class,
                value_converter_class=value_converter_class,
                value_converter_import=value_converter_import,
                from_java_func=from_java_func,
                from_java_func_import=from_java_func_import,
                setter_to_java_func=setter_to_java_func,
                setter_to_java_func_import=setter_to_java_func_import,
                is_deprecated=getter.is_deprecated,
            )
        )

    properties.sort(key=lambda p: p.python_name)
    cls.properties = properties


def nest_inner_classes(classes: list[ClassMeta]) -> list[ClassMeta]:
    by_fqn: dict[str, ClassMeta] = {c.java_fqn: c for c in classes}
    top_level: list[ClassMeta] = []

    for cls in classes:
        if "$" not in cls.java_fqn:
            top_level.append(cls)
            continue

        outer_fqn = cls.java_fqn.rsplit("$", 1)[0]
        outer = by_fqn.get(outer_fqn)
        if outer is not None:
            cls.is_inner = True
            outer.inner_classes.append(cls)
        else:
            outer_simple = outer_fqn.rsplit("/", 1)[-1].replace("$", "_")
            cls.python_class_name = f"{outer_simple}_{cls.python_class_name}"
            top_level.append(cls)

    return top_level
