"""Wrapper for my library `constrata` that adds some metadata factories for Soulstruct types."""

__all__ = [
    "BinaryStruct",
    "ByteOrder",
    "BinaryFieldTypeError",
    "BinaryFieldValueError",
    "BinaryReader",
    "BinaryWriter",

    "Binary",
    "binary",
    "BinaryString",
    "binary_string",
    "BinaryArray",
    "binary_array",
    "BinaryPad",
    "binary_pad",

    "byte",
    "uint8",
    "sbyte",
    "int8",
    "ushort",
    "uint16",
    "short",
    "int16",
    "uint",
    "uint32",
    "int32",
    "ulong",
    "uint64",
    "long",
    "int64",
    "single",
    "float32",
    "double",
    "float64",
    "varint",
    "varuint",
    "RESERVED",
]

from constrata import *

