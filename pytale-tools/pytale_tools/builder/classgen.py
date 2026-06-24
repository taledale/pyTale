"""Generates minimal JVM .class bytecode for plugin entry-point classes.

Each generated class extends ``AbstractPythonPlugin`` with a single
``public <init>(JavaPluginInit)`` constructor that delegates to ``super``.
"""

import struct

_SUPER_CLASS = "dev/taledale/pytale/AbstractPythonPlugin"
_INIT_NAME = "<init>"
_INIT_DESC = "(Lcom/hypixel/hytale/server/core/plugin/JavaPluginInit;)V"

_MAJOR_VERSION = 69
_ACC_PUBLIC = 0x0001
_ACC_SUPER = 0x0020

_CONSTANT_UTF8 = 1
_CONSTANT_CLASS = 7
_CONSTANT_NAME_AND_TYPE = 12
_CONSTANT_METHODREF = 10


def _utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">BH", _CONSTANT_UTF8, len(encoded)) + encoded


def _class_ref(name_index: int) -> bytes:
    return struct.pack(">BH", _CONSTANT_CLASS, name_index)


def _name_and_type(name_index: int, descriptor_index: int) -> bytes:
    return struct.pack(">BHH", _CONSTANT_NAME_AND_TYPE, name_index, descriptor_index)


def _methodref(class_index: int, nat_index: int) -> bytes:
    return struct.pack(">BHH", _CONSTANT_METHODREF, class_index, nat_index)


def generate_plugin_class(class_internal_name: str) -> bytes:
    """Build a ``.class`` file for a plugin entry-point.

    *class_internal_name* uses JVM internal form (slashes), e.g.
    ``taledale/test_plugin/TestPlugin``.
    """

    # --- constant pool (indices 1..9) ---
    pool = bytearray()
    pool += _methodref(2, 3)  # #1  super.<init>
    pool += _class_ref(4)  # #2  super class
    pool += _name_and_type(5, 6)  # #3  <init>:descriptor
    pool += _utf8(_SUPER_CLASS)  # #4
    pool += _utf8(_INIT_NAME)  # #5
    pool += _utf8(_INIT_DESC)  # #6
    pool += _class_ref(8)  # #7  this class
    pool += _utf8(class_internal_name)  # #8
    pool += _utf8("Code")  # #9
    cp_count = 10  # pool size + 1

    # --- constructor bytecode: aload_0, aload_1, invokespecial #1, return ---
    code = bytes([0x2A, 0x2B, 0xB7, 0x00, 0x01, 0xB1])
    code_attr = struct.pack(
        ">HIHHI",
        9,  # attribute_name_index → "Code"
        2 + 2 + 4 + len(code) + 2 + 2,  # attribute_length
        2,  # max_stack
        2,  # max_locals
        len(code),  # code_length
    )
    code_attr += code
    code_attr += struct.pack(">H", 0)  # exception_table_length
    code_attr += struct.pack(">H", 0)  # code sub-attributes count

    # --- method ---
    method = struct.pack(
        ">HHHH",
        _ACC_PUBLIC,  # access_flags
        5,  # name_index → <init>
        6,  # descriptor_index
        1,  # attributes_count
    )
    method += code_attr

    # --- assemble class file ---
    buf = bytearray()
    buf += struct.pack(">IHH", 0xCAFEBABE, 0, _MAJOR_VERSION)  # magic + version
    buf += struct.pack(">H", cp_count)
    buf += pool
    buf += struct.pack(">HHH", _ACC_PUBLIC | _ACC_SUPER, 7, 2)  # flags, this, super
    buf += struct.pack(">H", 0)  # interfaces_count
    buf += struct.pack(">H", 0)  # fields_count
    buf += struct.pack(">H", 1)  # methods_count
    buf += method
    buf += struct.pack(">H", 0)  # class attributes_count

    return bytes(buf)


def module_to_class_name(module_name: str) -> str:
    return "".join(part.title() for part in module_name.split("_"))
