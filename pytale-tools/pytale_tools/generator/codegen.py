from collections import defaultdict

from pytale_tools.exporter.models import ClassMeta
from pytale_tools.generator.analyzer import PropertySpec


def _base_classes(
    cls: ClassMeta, known_classes: dict[str, str], default_base: str = "BaseEvent"
) -> str:
    bases: list[str] = []
    parent = known_classes.get(cls.super_class) if cls.super_class else None
    if parent is not None:
        bases.append(parent)
    elif cls.is_async_event:
        bases.append("AsyncEvent")
    elif cls.is_sync_event:
        bases.append("Event")
    if cls.is_cancellable and "Cancellable" not in bases:
        bases.append("Cancellable")
    return ", ".join(bases) if bases else default_base


def _java_type_var_name(cls: ClassMeta) -> str:
    simple = cls.java_fqn.rsplit("/", 1)[-1]
    return f"_{simple.replace('$', '_')}"


def _generate_property(prop: PropertySpec, indent: str) -> list[str]:
    lines: list[str] = []
    lines.append(f"{indent}@property")
    lines.append(f"{indent}def {prop.python_name}(self) -> {prop.return_type}:")

    if prop.wrapper_class is not None:
        if prop.nullability.name == "NULLABLE":
            lines.append(f"{indent}    _value = self._java.{prop.getter_java_name}()")
            lines.append(
                f"{indent}    return {prop.wrapper_class}(_value) if _value is not None else None"
            )
        else:
            lines.append(
                f"{indent}    return {prop.wrapper_class}(self._java.{prop.getter_java_name}())"
            )
    elif prop.from_java_func is not None:
        if prop.nullability.name == "NULLABLE":
            lines.append(f"{indent}    _value = self._java.{prop.getter_java_name}()")
            lines.append(
                f"{indent}    return {prop.from_java_func}(_value) if _value is not None else None"
            )
        else:
            lines.append(
                f"{indent}    return {prop.from_java_func}(self._java.{prop.getter_java_name}())"
            )
    else:
        lines.append(f"{indent}    return self._java.{prop.getter_java_name}()")

    if prop.setter_java_name is not None and prop.setter_param_type is not None:
        lines.append("")
        lines.append(f"{indent}@{prop.python_name}.setter")
        lines.append(
            f"{indent}def {prop.python_name}(self, value: {prop.setter_param_type}) -> None:"
        )
        if prop.setter_wrapper_class is not None:
            lines.append(f"{indent}    self._java.{prop.setter_java_name}(value._java)")
        elif prop.setter_to_java_func is not None:
            lines.append(
                f"{indent}    self._java.{prop.setter_java_name}({prop.setter_to_java_func}(value))"
            )
        else:
            lines.append(f"{indent}    self._java.{prop.setter_java_name}(value)")

    return lines


def _generate_class(
    cls: ClassMeta,
    known_classes: dict[str, str],
    indent: str = "",
    default_base: str = "BaseEvent",
) -> list[str]:
    lines: list[str] = []
    bases = _base_classes(cls, known_classes, default_base)
    var_name = _java_type_var_name(cls)

    if cls.is_deprecated:
        lines.append(f'{indent}@deprecated("Deprecated in Java")')
    lines.append(f"{indent}class {cls.python_class_name}({bases}):")
    lines.append(f"{indent}    _java_class = {var_name}")

    has_body = bool(cls.properties) or bool(cls.inner_classes)

    for prop in cls.properties:
        lines.append("")
        lines.extend(_generate_property(prop, indent + "    "))

    for inner in cls.inner_classes:
        lines.append("")
        lines.extend(
            _generate_class(inner, known_classes, indent + "    ", default_base)
        )

    if not has_body:
        pass

    return lines


def _collect_java_types(cls: ClassMeta) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    var_name = _java_type_var_name(cls)
    result.append((var_name, cls.java_dotted))
    for inner in cls.inner_classes:
        result.extend(_collect_java_types(inner))
    return result


def _collect_all_properties(cls: ClassMeta) -> list[PropertySpec]:
    result = list(cls.properties)
    for inner in cls.inner_classes:
        result.extend(_collect_all_properties(inner))
    return result


def _uses_deprecated(classes: list[ClassMeta]) -> bool:
    for cls in classes:
        if cls.is_deprecated:
            return True
        for inner in cls.inner_classes:
            if _uses_deprecated([inner]):
                return True
    return False


def _uses_java_object(classes: list[ClassMeta]) -> bool:
    for cls in classes:
        for prop in _collect_all_properties(cls):
            if "JavaObject" in prop.return_type:
                return True
            if prop.setter_param_type and "JavaObject" in prop.setter_param_type:
                return True
    return False


def _collect_wrapper_imports(classes: list[ClassMeta]) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = defaultdict(set)
    for cls in classes:
        for prop in _collect_all_properties(cls):
            if prop.wrapper_import and prop.wrapper_class:
                imports[prop.wrapper_import].add(prop.wrapper_class)
            if prop.value_converter_import and prop.value_converter_class:
                imports[prop.value_converter_import].add(prop.value_converter_class)
            if prop.from_java_func_import and prop.from_java_func:
                imports[prop.from_java_func_import].add(prop.from_java_func)
            if prop.setter_to_java_func_import and prop.setter_to_java_func:
                imports[prop.setter_to_java_func_import].add(prop.setter_to_java_func)
    return dict(imports)


def generate_module(
    classes: list[ClassMeta],
    jar_name: str,
    base_module: str = "pytale.events",
    default_base: str = "BaseEvent",
) -> str:
    lines: list[str] = []
    lines.append(f"# Auto-generated by pytale-tools from {jar_name} — do not edit")

    needs_java_object = _uses_java_object(classes)
    needs_deprecated = _uses_deprecated(classes)
    if needs_java_object:
        lines.append("from typing import TYPE_CHECKING")
    if needs_deprecated:
        lines.append("from typing_extensions import deprecated")
    lines.append("")
    lines.append("import java as _java")

    known_classes_for_bases = _build_known_classes(classes)
    used_bases: set[str] = set()
    for cls in classes:
        _collect_bases(cls, used_bases, known_classes_for_bases, default_base)
    base_imports = sorted(used_bases)
    if base_imports:
        lines.append(f"from {base_module} import {', '.join(base_imports)}")

    wrapper_imports = _collect_wrapper_imports(classes)
    for module, names in sorted(wrapper_imports.items()):
        lines.append(f"from {module} import {', '.join(sorted(names))}")

    if needs_java_object:
        lines.append("")
        lines.append("if TYPE_CHECKING:")
        lines.append("    from java import JavaObject")

    all_types: list[tuple[str, str]] = []
    for cls in classes:
        all_types.extend(_collect_java_types(cls))

    for var_name, dotted in all_types:
        lines.append("")
        lines.append(f"{var_name} = _java.type(")
        lines.append(f'    "{dotted}"')
        lines.append(")")

    known_classes = _build_known_classes(classes)
    sorted_classes = sorted(
        classes, key=lambda c: (not c.is_abstract, c.python_class_name)
    )

    for cls in sorted_classes:
        lines.append("")
        lines.append("")
        lines.extend(_generate_class(cls, known_classes, default_base=default_base))

    lines.append("")
    return "\n".join(lines)


def _build_known_classes(classes: list[ClassMeta]) -> dict[str, str]:
    result: dict[str, str] = {}
    for cls in classes:
        result[cls.java_fqn] = cls.python_class_name
        for inner in cls.inner_classes:
            result[inner.java_fqn] = inner.python_class_name
    return result


def _collect_bases(
    cls: ClassMeta,
    bases: set[str],
    known_classes: dict[str, str],
    default_base: str = "BaseEvent",
) -> None:
    parent = known_classes.get(cls.super_class) if cls.super_class else None
    if parent is None:
        if cls.is_async_event:
            bases.add("AsyncEvent")
        elif cls.is_sync_event:
            bases.add("Event")
        else:
            bases.add(default_base)
    if cls.is_cancellable:
        bases.add("Cancellable")
    for inner in cls.inner_classes:
        _collect_bases(inner, bases, known_classes, default_base)


def _get_package_path(cls: ClassMeta) -> str:
    base_fqn = cls.java_fqn.split("$")[0]
    parts = base_fqn.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _find_common_prefix(paths: list[str]) -> str:
    if not paths:
        return ""
    split_paths = [p.split("/") for p in paths]
    prefix_parts: list[str] = []
    for segments in zip(*split_paths):
        if len(set(segments)) == 1:
            prefix_parts.append(segments[0])
        else:
            break
    if not prefix_parts:
        return ""
    return "/".join(prefix_parts) + "/"


def group_by_package(classes: list[ClassMeta]) -> dict[str, list[ClassMeta]]:
    package_paths = list({_get_package_path(cls) for cls in classes})
    common_prefix = _find_common_prefix(package_paths)

    groups: dict[str, list[ClassMeta]] = defaultdict(list)
    for cls in classes:
        pkg = _get_package_path(cls)
        relative = pkg[len(common_prefix) :]
        if not relative:
            relative = "misc"
        groups[relative].append(cls)
    return dict(groups)
