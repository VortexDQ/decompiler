#!/usr/bin/env python3
"""
================================================================================
 Luau Bytecode Decompiler Tool  - Educational Edition
 Done by vortexdq
================================================================================
A local, safe tool for decompiling Roblox Luau bytecode to readable source code.

Features:
  - Decompile Luau bytecode to readable Luau source
  - Disassembly view for low-level inspection
  - HTTP API for programmatic use (localhost only)
  - Multiple input formats: raw .luac, base64, hex, .rbmx/.rbm (Roblox XML model)
  - Batch processing of folders
  - Configurable formatting options (config.json)
  - Robust, specific error handling (no bare excepts)
  - 100% local, no telemetry, no network calls except your own localhost server

Author: vortexdq
================================================================================
"""

import sys
import os
import json
import base64
import struct
import argparse
import logging
import binascii
import re
import ast
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum, IntEnum
import xml.etree.ElementTree as ET

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# ----------------------------------------------------------------------------- 
# Metadata
# -----------------------------------------------------------------------------

__version__ = "2.0.0"
__author__ = "vortexdq"
__tool_name__ = "Luau Bytecode Decompiler Tool - 10x Edition"

BANNER = f"""
==============================================================================
 {__tool_name__}
 Version {__version__}  |  Done by vortexdq
==============================================================================
"""

# ----------------------------------------------------------------------------- 
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vortexdq.decompiler")


# ----------------------------------------------------------------------------- 
# Exceptions
# -----------------------------------------------------------------------------

class DecompileError(Exception):
    """Raised when decompilation fails for a known reason."""
    pass


class BytecodeFormatError(DecompileError):
    """Raised when bytecode format is invalid or unsupported."""
    pass


class RbmxParseError(DecompileError):
    """Raised when an .rbmx/.rbm XML model cannot be parsed."""
    pass


# ----------------------------------------------------------------------------- 
# Options
# -----------------------------------------------------------------------------

@dataclass
class DecompileOptions:
    """Decompilation formatting options."""
    semicolons: bool = False
    string_interpolation: bool = True
    comments_for_upvalues: bool = True
    original_line_info: bool = True
    function_id: bool = True
    preserve_numeric_loop_steps: bool = True
    use_if_expressions: bool = True
    indent_size: int = 2
    include_header: bool = True
    include_disassembly_comments: bool = False
    safe_mode: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecompileOptions":
        """Build options from a dict, ignoring unknown keys."""
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in (data or {}).items() if k in valid}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- 
# Bytecode Reader
# -----------------------------------------------------------------------------

class BytecodeReader:
    """Low-level bytecode reader with bounds checking and position tracking."""

    def __init__(self, data: bytes):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("BytecodeReader expects bytes")
        self.data = bytes(data)
        self.position = 0
        self.size = len(data)

    def remaining(self) -> int:
        return self.size - self.position

    def read_byte(self) -> int:
        if self.position >= self.size:
            raise BytecodeFormatError(f"Unexpected EOF at position {self.position}")
        val = self.data[self.position]
        self.position += 1
        return val

    def read_bytes(self, count: int) -> bytes:
        if count < 0:
            raise ValueError("count must be non-negative")
        if self.position + count > self.size:
            raise BytecodeFormatError(
                f"Unexpected EOF: need {count} bytes at position {self.position}"
            )
        val = self.data[self.position:self.position + count]
        self.position += count
        return val

    def read_uleb128(self) -> int:
        """Read unsigned LEB128."""
        result = 0
        shift = 0
        while True:
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift > 63:
                raise BytecodeFormatError("uleb128 too large")
        return result

    def read_sleb128(self) -> int:
        """Read signed LEB128."""
        result = 0
        shift = 0
        byte = 0
        while True:
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift
            shift += 7
            if (byte & 0x80) == 0:
                break
            if shift > 64:
                raise BytecodeFormatError("sleb128 too large")
        if (byte & 0x40) != 0 and shift < 64:
            result |= -(1 << shift)
        return result

    def read_string(self) -> str:
        """Read a length-prefixed UTF-8 string."""
        length = self.read_uleb128()
        if length == 0:
            return ""
        data = self.read_bytes(length)
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            return data.hex()

    def read_double(self) -> float:
        return struct.unpack('<d', self.read_bytes(8))[0]

    def read_float(self) -> float:
        return struct.unpack('<f', self.read_bytes(4))[0]

    def read_int(self) -> int:
        return struct.unpack('<i', self.read_bytes(4))[0]

    def read_uint(self) -> int:
        return struct.unpack('<I', self.read_bytes(4))[0]

    def peek_byte(self) -> int:
        if self.position >= self.size:
            return -1
        return self.data[self.position]

    def skip(self, count: int):
        if self.position + count > self.size:
            raise BytecodeFormatError(
                f"Cannot skip {count} bytes at position {self.position}"
            )
        self.position += count


# ----------------------------------------------------------------------------- 
# Luau Opcodes (complete table)
# -----------------------------------------------------------------------------

class LuauOpcode(IntEnum):
    """Complete Luau opcode table (ordered as in Luau source)."""
    NOP = 0
    BREAK = 1
    LOADNIL = 2
    LOADB = 3
    LOADN = 4
    LOADK = 5
    MOVE = 6
    GETGLOBAL = 7
    SETGLOBAL = 8
    GETUPVAL = 9
    SETUPVAL = 10
    CLOSEUPVALS = 11
    GETTABLE = 12
    SETTABLE = 13
    GETTABLEKS = 14
    SETTABLEKS = 15
    GETIMPORT = 16
    CONCAT = 17
    UNM = 18
    NOT = 19
    LENGTH = 20
    NEWTABLE = 21
    DUPTABLE = 22
    SETLIST = 23
    ADD = 24
    SUB = 25
    MUL = 26
    DIV = 27
    MOD = 28
    POW = 29
    ADDK = 30
    SUBK = 31
    MULK = 32
    DIVK = 33
    MODK = 34
    POWK = 35
    AND = 36
    OR = 37
    JUMP = 38
    JUMPIF = 39
    JUMPIFNOT = 40
    JUMPIFEQ = 41
    JUMPIFLE = 42
    JUMPIFLT = 43
    JUMPIFNOTEQ = 44
    JUMPIFNOTLE = 45
    JUMPIFNOTLT = 46
    CALL = 47
    RETURN = 48
    FORLOOP = 49
    FORPREP = 50
    TFORLOOP = 51
    TFORPREP = 52
    SETTABLEN = 53
    NEWCLOSURE = 54
    GETENV = 55
    GETVARARGS = 56
    DUPCLOSURE = 57
    PREPVARARGS = 58
    LOADKX = 59
    JUMPX = 60
    FASTCALL = 61
    COVERAGE = 62
    CAPTURE = 63
    SUBRK = 64
    DIVRK = 65
    MODRK = 66
    POWRK = 67
    ADDKT = 68
    SUBKT = 69
    MULKT = 70
    DIVKT = 71
    MODKT = 72
    POWKT = 73


OPCODE_NAMES = {op.value: op.name for op in LuauOpcode}


# ----------------------------------------------------------------------------- 
# Instruction & Function
# -----------------------------------------------------------------------------

@dataclass
class LuauInstruction:
    """A single Luau bytecode instruction."""
    opcode: int
    a: int
    b: int
    c: int
    offset: int
    size: int = 4

    @property
    def opcode_name(self) -> str:
        return OPCODE_NAMES.get(self.opcode, f'UNKNOWN_{self.opcode}')

    def __repr__(self):
        return (f"{self.offset:06x}: {self.opcode_name:14s} "
                f"A={self.a:3d} B={self.b:3d} C={self.c:3d}")


@dataclass
class LuauFunction:
    """Represents a Luau function parsed from bytecode."""
    name: str = ""
    line_defined: int = 0
    last_line_defined: int = 0
    num_params: int = 0
    is_vararg: bool = False
    max_stack_size: int = 0
    code: List[LuauInstruction] = field(default_factory=list)
    constants: List[Any] = field(default_factory=list)
    upvalues: List[Tuple[bool, int, str]] = field(default_factory=list)
    functions: List["LuauFunction"] = field(default_factory=list)
    debug_info: Dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def disassemble(self, indent: int = 0) -> str:
        """Generate disassembly output."""
        pad = "  " * indent
        lines = [
            f"{pad}Function: {self.name or '<anonymous>'}",
            f"{pad}Line: {self.line_defined}-{self.last_line_defined}",
            f"{pad}Params: {self.num_params}, Vararg: {self.is_vararg}",
            f"{pad}Max Stack: {self.max_stack_size}",
            f"{pad}Constants:",
        ]
        for i, const in enumerate(self.constants):
            lines.append(f"{pad}  {i}: {self._format_constant(const)}")
        lines.append(f"{pad}Upvalues:")
        for i, upv in enumerate(self.upvalues):
            instack, idx, name = upv
            lines.append(f"{pad}  {i}: {name} (instack={instack}, idx={idx})")
        lines.append(f"{pad}Instructions:")
        for instr in self.code:
            lines.append(f"{pad}  {instr}")
        lines.append("")
        for child in self.functions:
            lines.append(child.disassemble(indent + 1))
        return "\n".join(lines)

    @staticmethod
    def _format_constant(const: Any) -> str:
        if const is None:
            return "nil"
        if isinstance(const, bool):
            return "true" if const else "false"
        if isinstance(const, float):
            if const == int(const) and abs(const) < 1e15:
                return f"{int(const)}.0"
            return repr(const)
        return repr(const)


# ----------------------------------------------------------------------------- 
# Rbmx / Rbm XML model parsing
# -----------------------------------------------------------------------------

def extract_bytecode_from_rbmx(path: str) -> List[Tuple[str, bytes]]:
    """
    Parse a Roblox .rbmx/.rbm XML model file and extract any embedded
    bytecode chunks (base64-encoded <BinaryString> or <Script> blocks).

    Returns a list of (name, bytecode_bytes) tuples.
    """
    results: List[Tuple[str, bytes]] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise RbmxParseError(f"Invalid XML in {path}: {e}")
    except FileNotFoundError:
        raise RbmxParseError(f"File not found: {path}")

    root = tree.getroot()

    # Roblox files use a 'roblox' namespace sometimes; strip it for matching.
    def local_name(tag: str) -> str:
        return tag.split('}', 1)[-1] if '}' in tag else tag

    def walk(node):
        lname = local_name(node.tag)
        # A Script / LocalScript / ModuleScript may carry a name attribute
        script_name = node.attrib.get('name', '')

        # Look for bytecode in <BinaryString> children or attributes
        for child in node:
            cname = local_name(child.tag)
            if cname in ('BinaryString', 'ProtectedString', 'Bytecode'):
                text = (child.text or '').strip()
                if not text:
                    continue
                # Try base64
                try:
                    decoded = base64.b64decode(text)
                except (binascii.Error, ValueError):
                    continue
                # Heuristic: looks like Luau bytecode
                if decoded[:4] == b'LuaU' or len(decoded) > 8:
                    label = script_name or f"chunk_{len(results)}"
                    results.append((label, decoded))

        # Recurse
        for child in node:
            walk(child)

    walk(root)

    if not results:
        # Fallback: scan raw file text for base64-looking blobs that decode to LuaU
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                raw = f.read()
        except OSError as e:
            raise RbmxParseError(f"Cannot read {path}: {e}")
        for match in re.finditer(r'[A-Za-z0-9+/=]{40,}', raw):
            try:
                decoded = base64.b64decode(match.group(0))
                if decoded[:4] == b'LuaU':
                    results.append((f"chunk_{len(results)}", decoded))
            except (binascii.Error, ValueError):
                continue

    if not results:
        raise RbmxParseError(
            f"No embedded Luau bytecode found in {path}. "
            "The file may contain plain Lua source instead of compiled bytecode."
        )
    return results


# ----------------------------------------------------------------------------- 
# Decompiler
# -----------------------------------------------------------------------------

class LuauDecompiler:
    """Main decompiler implementation."""

    # Opcodes that produce a value into register A
    VALUE_PRODUCING = {
        LuauOpcode.LOADNIL, LuauOpcode.LOADB, LuauOpcode.LOADN, LuauOpcode.LOADK,
        LuauOpcode.LOADKX, LuauOpcode.MOVE, LuauOpcode.GETGLOBAL, LuauOpcode.GETUPVAL,
        LuauOpcode.GETTABLE, LuauOpcode.GETTABLEKS, LuauOpcode.GETIMPORT,
        LuauOpcode.NEWTABLE, LuauOpcode.DUPTABLE, LuauOpcode.ADD, LuauOpcode.SUB,
        LuauOpcode.MUL, LuauOpcode.DIV, LuauOpcode.MOD, LuauOpcode.POW,
        LuauOpcode.ADDK, LuauOpcode.SUBK, LuauOpcode.MULK, LuauOpcode.DIVK,
        LuauOpcode.MODK, LuauOpcode.POWK, LuauOpcode.UNM, LuauOpcode.NOT,
        LuauOpcode.LENGTH, LuauOpcode.CONCAT, LuauOpcode.GETENV, LuauOpcode.GETVARARGS,
        LuauOpcode.CALL, LuauOpcode.DUPCLOSURE, LuauOpcode.NEWCLOSURE,
    }

    def __init__(self, options: Optional[DecompileOptions] = None):
        self.options = options or DecompileOptions()
        self.indent_level = 0
        self._reg_names: Dict[int, str] = {}
        self._reg_counter = 0

    # -- public API ---------------------------------------------------------

    def decompile(self, bytecode: bytes) -> str:
        """Decompile bytecode to Luau source."""
        header = ""
        if self.options.include_header:
            header = (
                "--============================================================================\n"
                "-- Decompiled with Luau Bytecode Decompiler Tool (10x Edition)\n"
                f"-- Version {__version__} | Done by vortexdq\n"
                "--============================================================================\n\n"
            )
        try:
            reader = BytecodeReader(bytecode)
            functions = self._parse_functions(reader)
            if not functions:
                return header + "-- No functions found in bytecode\n"

            parts = [header] if header else []
            for i, func in enumerate(functions):
                if i > 0:
                    parts.append("\n")
                parts.append(self._decompile_function(func, top_level=(i == 0)))
            return "".join(parts)
        except DecompileError as e:
            return header + f"-- DECOMPILATION ERROR: {e}\n"
        except Exception as e:
            logger.error("Unexpected error during decompilation: %s", e, exc_info=True)
            return header + f"-- UNEXPECTED ERROR: {e}\n"

    def disassemble(self, bytecode: bytes) -> str:
        """Generate disassembly of bytecode."""
        header = ""
        if self.options.include_header:
            header = (
                ";============================================================================\n"
                "; Disassembly - Luau Bytecode Decompiler Tool (10x Edition)\n"
                f"; Version {__version__} | Done by vortexdq\n"
                ";============================================================================\n\n"
            )
        try:
            reader = BytecodeReader(bytecode)
            functions = self._parse_functions(reader)
            if not functions:
                return header + "No functions found in bytecode\n"

            out = [header] if header else []
            for i, func in enumerate(functions):
                out.append(f"=== Function {i} ===\n")
                out.append(func.disassemble())
            return "".join(out)
        except DecompileError as e:
            return header + f"DISASSEMBLY ERROR: {e}\n"
        except Exception as e:
            logger.error("Unexpected error during disassembly: %s", e, exc_info=True)
            return header + f"UNEXPECTED ERROR: {e}\n"

    # -- parsing ------------------------------------------------------------

    def _parse_functions(self, reader: BytecodeReader) -> List[LuauFunction]:
        """Parse function definitions from bytecode."""
        functions: List[LuauFunction] = []

        # Luau bytecode signature: 'LuaU'
        if reader.remaining() >= 4 and reader.data[:4] == b'LuaU':
            try:
                reader.read_bytes(4)  # signature
                version = reader.read_byte()
                logger.debug("Luau version: %s", version)
                # Skip feature flags (16 bytes) if present
                if reader.remaining() >= 16:
                    reader.skip(16)
                func = self._parse_function(reader)
                functions.append(func)
                # Additional top-level functions (rare)
                while reader.remaining() > 0:
                    try:
                        func = self._parse_function(reader)
                        functions.append(func)
                    except BytecodeFormatError:
                        break
            except BytecodeFormatError as e:
                logger.warning("Header parse failed: %s", e)
                if not functions:
                    raise
        else:
            # Try raw bytecode without header
            logger.info("No LuaU header; attempting raw bytecode parse")
            reader.position = 0
            func = self._parse_function_raw(reader)
            functions.append(func)

        return functions

    def _parse_function(self, reader: BytecodeReader) -> LuauFunction:
        """Parse a single function from Luau bytecode."""
        func = LuauFunction()

        func.name = reader.read_string()
        func.line_defined = reader.read_int()
        func.last_line_defined = reader.read_int()
        func.num_params = reader.read_byte()
        func.is_vararg = bool(reader.read_byte())
        func.max_stack_size = reader.read_byte()

        # Code
        code_size = reader.read_uint()
        if code_size > 5_000_000:
            raise BytecodeFormatError(f"Implausible code size: {code_size}")
        for i in range(code_size):
            opcode = reader.read_byte()
            a = reader.read_byte()
            b = reader.read_byte()
            c = reader.read_byte()
            func.code.append(LuauInstruction(opcode, a, b, c, offset=i * 4))

        # Constants
        num_constants = reader.read_uint()
        if num_constants > 5_000_000:
            raise BytecodeFormatError(f"Implausible constant count: {num_constants}")
        for _ in range(num_constants):
            const_type = reader.read_byte()
            if const_type == 0:    # NIL
                func.constants.append(None)
            elif const_type == 1:  # BOOLEAN
                func.constants.append(bool(reader.read_byte()))
            elif const_type == 2:  # NUMBER (double)
                func.constants.append(reader.read_double())
            elif const_type == 3:  # STRING
                func.constants.append(reader.read_string())
            elif const_type == 4:  # INTEGER
                func.constants.append(reader.read_int())
            elif const_type == 5:  # VECTOR
                x = reader.read_float()
                y = reader.read_float()
                z = reader.read_float()
                func.constants.append(("Vector3", x, y, z))
            elif const_type == 6:  # FUNCTION ref
                reader.skip(4)
                func.constants.append("<function>")
            else:
                func.constants.append(f"<unknown type {const_type}>")

        # Upvalues
        num_upvalues = reader.read_uint()
        for _ in range(num_upvalues):
            instack = bool(reader.read_byte())
            idx = reader.read_byte()
            name = reader.read_string()
            func.upvalues.append((instack, idx, name or f"upvalue_{idx}"))

        # Child functions
        num_children = reader.read_uint()
        if num_children > 1_000_000:
            raise BytecodeFormatError(f"Implausible child count: {num_children}")
        for _ in range(num_children):
            func.functions.append(self._parse_function(reader))

        return func

    def _parse_function_raw(self, reader: BytecodeReader) -> LuauFunction:
        """Best-effort parse of raw bytecode without a header."""
        func = LuauFunction()
        func.name = f"raw_function_{reader.size}"
        if reader.size >= 4:
            code_size = struct.unpack('<I', reader.read_bytes(4))[0]
            limit = min(code_size, 10000)  # safety cap
            for i in range(limit):
                if reader.remaining() < 4:
                    break
                opcode = reader.read_byte()
                a = reader.read_byte()
                b = reader.read_byte()
                c = reader.read_byte()
                func.code.append(LuauInstruction(opcode, a, b, c, offset=i * 4))
        return func

    # -- decompilation ------------------------------------------------------

    def _indent(self) -> str:
        return " " * (self.options.indent_size * self.indent_level)

    def _reg_name(self, idx: int) -> str:
        if idx in self._reg_names:
            return self._reg_names[idx]
        name = f"r{idx}"
        self._reg_names[idx] = name
        return name

    def _format_constant(self, const: Any) -> str:
        if const is None:
            return "nil"
        if isinstance(const, bool):
            return "true" if const else "false"
        if isinstance(const, str):
            # Escape for Lua string
            escaped = const.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            return f'"{escaped}"'
        if isinstance(const, float):
            if const == int(const) and abs(const) < 1e15:
                return f"{int(const)}"
            return repr(const)
        if isinstance(const, int):
            return str(const)
        if isinstance(const, tuple) and const and const[0] == "Vector3":
            return f"Vector3.new({const[1]}, {const[2]}, {const[3]})"
        return repr(const)

    def _operand_value(self, instr: LuauInstruction, func: LuauFunction, operand: str) -> str:
        """Resolve an operand to a source expression."""
        if operand == 'A':
            return self._reg_name(instr.a)
        if operand == 'B':
            return self._reg_name(instr.b)
        if operand == 'C':
            return self._reg_name(instr.c)
        if operand == 'Bk':
            if instr.b < len(func.constants):
                return self._format_constant(func.constants[instr.b])
            return f"K{instr.b}"
        if operand == 'Ck':
            if instr.c < len(func.constants):
                return self._format_constant(func.constants[instr.c])
            return f"K{instr.c}"
        return "?"

    def _decompile_function(self, func: LuauFunction, top_level: bool = False) -> str:
        """Decompile a function to source code."""
        self._reg_names = {}
        self._reg_counter = 0
        lines: List[str] = []

        # Optional function-id comment
        if self.options.function_id:
            fid = func.name or f"func_{id(func) & 0xFFFF:x}"
            lines.append(f"-- Function: {fid}  (lines {func.line_defined}-{func.last_line_defined})")

        # Upvalue comments
        if self.options.comments_for_upvalues and func.upvalues:
            upv_str = ", ".join(name for _, _, name in func.upvalues)
            lines.append(f"-- Upvalues: {upv_str}")

        # Build signature
        params = [f"a{i}" for i in range(func.num_params)]
        if func.is_vararg:
            params.append("...")
        fname = func.name if func.name and not func.name.startswith("<") else "_main"
        if top_level and (not func.name or func.name.startswith("<")):
            # Main chunk - no function wrapper, just a do...end block
            lines.append("do")
            self.indent_level = 1
        else:
            lines.append(f"function {fname}({', '.join(params)})")
            self.indent_level = 1

        # Walk instructions
        for instr in func.code:
            src = self._instruction_to_source(instr, func)
            if src:
                for s in src:
                    lines.append(f"{self._indent()}{s}")

        self.indent_level = 0
        if top_level and (not func.name or func.name.startswith("<")):
            lines.append("end -- main chunk")
        else:
            lines.append("end")

        # Child functions
        for child in func.functions:
            lines.append("")
            lines.append(self._decompile_function(child, top_level=False))

        return "\n".join(lines) + "\n"

    def _instruction_to_source(self, instr: LuauInstruction, func: LuauFunction) -> List[str]:
        """Translate a single instruction to one or more source lines."""
        op = instr.opcode
        A = self._reg_name(instr.a)
        B = self._reg_name(instr.b)
        C = self._reg_name(instr.c)
        Bk = self._operand_value(instr, func, 'Bk')
        Ck = self._operand_value(instr, func, 'Ck')
        term = ";" if self.options.semicolons else ""

        try:
            if op == LuauOpcode.NOP:
                return [] if not self.options.include_disassembly_comments else [f"-- NOP"]
            if op == LuauOpcode.BREAK:
                return [f"break{term}"]
            if op == LuauOpcode.LOADNIL:
                return [f"local {A} = nil{term}"]
            if op == LuauOpcode.LOADB:
                return [f"local {A} = {('true' if instr.b else 'false')}{term}"]
            if op == LuauOpcode.LOADN:
                # LOADN loads a signed 16-bit from B/C combined
                val = instr.b | (instr.c << 8)
                if val >= 0x8000:
                    val -= 0x10000
                return [f"local {A} = {val}{term}"]
            if op == LuauOpcode.LOADK:
                return [f"local {A} = {Bk}{term}"]
            if op == LuauOpcode.LOADKX:
                return [f"local {A} = {Ck}{term}"]
            if op == LuauOpcode.MOVE:
                return [f"local {A} = {B}{term}"]
            if op == LuauOpcode.GETGLOBAL:
                return [f"local {A} = {Bk}{term}  -- global"]
            if op == LuauOpcode.SETGLOBAL:
                return [f"{Bk} = {A}{term}  -- global"]
            if op == LuauOpcode.GETUPVAL:
                upv = func.upvalues[instr.b][2] if instr.b < len(func.upvalues) else f"upval{instr.b}"
                return [f"local {A} = {upv}{term}  -- upvalue"]
            if op == LuauOpcode.SETUPVAL:
                upv = func.upvalues[instr.a][2] if instr.a < len(func.upvalues) else f"upval{instr.a}"
                return [f"{upv} = {B}{term}  -- upvalue"]
            if op == LuauOpcode.GETTABLE:
                return [f"local {A} = {B}[{C}]{term}"]
            if op == LuauOpcode.SETTABLE:
                return [f"{B}[{C}] = {A}{term}"]
            if op == LuauOpcode.GETTABLEKS:
                return [f"local {A} = {B}.{Ck}{term}"]
            if op == LuauOpcode.SETTABLEKS:
                return [f"{B}.{Ck} = {A}{term}"]
            if op == LuauOpcode.GETIMPORT:
                return [f"local {A} = {Bk}{term}  -- import"]
            if op == LuauOpcode.CONCAT:
                return [f"local {A} = {B} .. {C}{term}"]
            if op == LuauOpcode.UNM:
                return [f"local {A} = -{B}{term}"]
            if op == LuauOpcode.NOT:
                return [f"local {A} = not {B}{term}"]
            if op == LuauOpcode.LENGTH:
                return [f"local {A} = #{B}{term}"]
            if op == LuauOpcode.NEWTABLE:
                return [f"local {A} = {{}}{term}"]
            if op == LuauOpcode.DUPTABLE:
                return [f"local {A} = {{}}{term}  -- dup"]
            if op == LuauOpcode.SETLIST:
                return [f"-- SETLIST {A} {B} {C}"]
            if op in (LuauOpcode.ADD, LuauOpcode.ADDK):
                rhs = Bk if op == LuauOpcode.ADDK else B
                rhs2 = Ck if op == LuauOpcode.ADDK else C
                return [f"local {A} = {rhs} + {rhs2}{term}"]
            if op in (LuauOpcode.SUB, LuauOpcode.SUBK):
                rhs = Bk if op == LuauOpcode.SUBK else B
                rhs2 = Ck if op == LuauOpcode.SUBK else C
                return [f"local {A} = {rhs} - {rhs2}{term}"]
            if op in (LuauOpcode.MUL, LuauOpcode.MULK):
                rhs = Bk if op == LuauOpcode.MULK else B
                rhs2 = Ck if op == LuauOpcode.MULK else C
                return [f"local {A} = {rhs} * {rhs2}{term}"]
            if op in (LuauOpcode.DIV, LuauOpcode.DIVK):
                rhs = Bk if op == LuauOpcode.DIVK else B
                rhs2 = Ck if op == LuauOpcode.DIVK else C
                return [f"local {A} = {rhs} / {rhs2}{term}"]
            if op in (LuauOpcode.MOD, LuauOpcode.MODK):
                rhs = Bk if op == LuauOpcode.MODK else B
                rhs2 = Ck if op == LuauOpcode.MODK else C
                return [f"local {A} = {rhs} % {rhs2}{term}"]
            if op in (LuauOpcode.POW, LuauOpcode.POWK):
                rhs = Bk if op == LuauOpcode.POWK else B
                rhs2 = Ck if op == LuauOpcode.POWK else C
                return [f"local {A} = {rhs} ^ {rhs2}{term}"]
            if op == LuauOpcode.AND:
                return [f"local {A} = {B} and {C}{term}"]
            if op == LuauOpcode.OR:
                return [f"local {A} = {B} or {C}{term}"]
            if op == LuauOpcode.JUMP:
                return [f"-- jump {instr.b}"]
            if op == LuauOpcode.JUMPIF:
                return [f"if {A} then{term}  -- jump"]
            if op == LuauOpcode.JUMPIFNOT:
                return [f"if not {A} then{term}  -- jump"]
            if op == LuauOpcode.JUMPIFEQ:
                return [f"-- if {A} == {B} then jump"]
            if op == LuauOpcode.JUMPIFLE:
                return [f"-- if {A} <= {B} then jump"]
            if op == LuauOpcode.JUMPIFLT:
                return [f"-- if {A} < {B} then jump"]
            if op == LuauOpcode.JUMPIFNOTEQ:
                return [f"-- if {A} ~= {B} then jump"]
            if op == LuauOpcode.JUMPIFNOTLE:
                return [f"-- if {A} > {B} then jump"]
            if op == LuauOpcode.JUMPIFNOTLT:
                return [f"-- if {A} >= {B} then jump"]
            if op == LuauOpcode.CALL:
                nargs = instr.b - 1
                nrets = instr.c - 1
                args = ", ".join(self._reg_name(instr.a + 1 + i) for i in range(max(nargs, 0)))
                if nrets <= 0:
                    return [f"{A}({args}){term}"]
                elif nrets == 1:
                    return [f"local {A} = {A}({args}){term}"]
                else:
                    rets = ", ".join(self._reg_name(instr.a + i) for i in range(nrets))
                    return [f"local {rets} = {A}({args}){term}"]
            if op == LuauOpcode.RETURN:
                nrets = instr.b - 1
                if nrets <= 0:
                    return [f"return{term}"]
                elif nrets == 1:
                    return [f"return {A}{term}"]
                else:
                    rets = ", ".join(self._reg_name(instr.a + i) for i in range(nrets))
                    return [f"return {rets}{term}"]
            if op == LuauOpcode.FORLOOP:
                return [f"-- forloop {A}"]
            if op == LuauOpcode.FORPREP:
                return [f"-- forprep {A}"]
            if op == LuauOpcode.TFORLOOP:
                return [f"-- tforloop {A}"]
            if op == LuauOpcode.TFORPREP:
                return [f"-- tforprep {A}"]
            if op == LuauOpcode.NEWCLOSURE:
                return [f"local {A} = {Bk}{term}  -- closure"]
            if op == LuauOpcode.DUPCLOSURE:
                return [f"local {A} = {Bk}{term}  -- dupclosure"]
            if op == LuauOpcode.GETENV:
                return [f"local {A} = getfenv(){term}"]
            if op == LuauOpcode.GETVARARGS:
                return [f"local {A} = ...{term}"]
            if op == LuauOpcode.PREPVARARGS:
                return [f"-- prepvarargs {instr.a}"]
            if op == LuauOpcode.JUMPX:
                return [f"-- jumpx {instr.b}"]
            if op == LuauOpcode.FASTCALL:
                return [f"-- fastcall {instr.a}"]
            if op == LuauOpcode.COVERAGE:
                return [f"-- coverage {instr.a}"]
            if op == LuauOpcode.CAPTURE:
                return [f"-- capture {instr.a} {instr.b}"]
            if op == LuauOpcode.CLOSEUPVALS:
                return [f"-- closeupvals {instr.a}"]
            # Unknown / unhandled
            return [f"-- {instr.opcode_name} A={instr.a} B={instr.b} C={instr.c}"]
        except Exception as e:
            logger.debug("Failed to translate instruction %s: %s", instr, e)
            return [f"-- {instr.opcode_name} (translation error)"]


# ----------------------------------------------------------------------------- 
# HTTP Server
# -----------------------------------------------------------------------------

class DecompilerServer:
    """HTTP API server for the decompiler (localhost only)."""

    def __init__(self, decompiler: LuauDecompiler, options: DecompileOptions):
        self.decompiler = decompiler
        self.options = options
        self.app = Flask(__name__) if FLASK_AVAILABLE else None
        if self.app:
            self._setup_routes()

    def _setup_routes(self):
        if not self.app:
            return

        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'ok',
                'tool': __tool_name__,
                'version': __version__,
                'author': __author__,
            })

        @self.app.route('/info', methods=['GET'])
        def info():
            return jsonify({
                'name': __tool_name__,
                'version': __version__,
                'author': __author__,
                'flask_available': FLASK_AVAILABLE,
                'options': self.options.to_dict(),
            })

        @self.app.route('/decompile', methods=['POST'])
        def decompile_endpoint():
            try:
                data = request.get_json(silent=True)
                if not data:
                    return jsonify({'error': 'No JSON data provided'}), 400

                bytecode_input = data.get('bytecode')
                if not bytecode_input:
                    return jsonify({'error': 'No bytecode provided'}), 400

                # Decode input
                if isinstance(bytecode_input, str):
                    try:
                        bytecode = base64.b64decode(bytecode_input, validate=True)
                    except (binascii.Error, ValueError):
                        bytecode = bytecode_input.encode('utf-8')
                elif isinstance(bytecode_input, list):
                    bytecode = bytes(bytecode_input)
                else:
                    return jsonify({'error': 'bytecode must be base64 string or byte list'}), 400

                options = DecompileOptions.from_dict(data.get('options', {}))
                decompiler = LuauDecompiler(options)

                mode = data.get('mode', 'decompile')
                if mode == 'disassemble':
                    result = decompiler.disassemble(bytecode)
                else:
                    result = decompiler.decompile(bytecode)

                return jsonify({
                    'success': True,
                    'result': result,
                    'mode': mode,
                    'author': __author__,
                    'version': __version__,
                })
            except DecompileError as e:
                return jsonify({'success': False, 'error': str(e)}), 400
            except Exception as e:
                logger.error("API error: %s", e, exc_info=True)
                return jsonify({'success': False, 'error': str(e)}), 500

    def run(self, host: str = '127.0.0.1', port: int = 5000):
        if not self.app:
            logger.error("Flask not available - cannot start HTTP server. "
                         "Install with: pip install flask")
            return
        # Safety: never bind to 0.0.0.0 by default
        if host in ('0.0.0.0', '::'):
            logger.warning("Refusing to bind to %s; forcing 127.0.0.1 for safety", host)
            host = '127.0.0.1'
        logger.info("Starting HTTP server on %s:%d (Done by vortexdq)", host, port)
        self.app.run(host=host, port=port, debug=False)


# ----------------------------------------------------------------------------- 
# Input / Output helpers
# -----------------------------------------------------------------------------

def process_input(input_data: str, is_file: bool = False) -> bytes:
    """Process input data (file or string) to get bytecode bytes."""
    if is_file:
        path = Path(input_data)
        if not path.exists():
            raise DecompileError(f"File not found: {input_data}")
        try:
            return path.read_bytes()
        except OSError as e:
            raise DecompileError(f"Error reading file {input_data}: {e}")
    # String input
    stripped = input_data.strip()
    # base64
    try:
        return base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        pass
    # hex with 0x prefix
    if stripped.lower().startswith('0x'):
        try:
            return bytes.fromhex(stripped[2:])
        except ValueError:
            pass
    # plain hex
    if re.fullmatch(r'[0-9a-fA-F]+', stripped) and len(stripped) % 2 == 0:
        try:
            return bytes.fromhex(stripped)
        except ValueError:
            pass
    # Python byte list
    if stripped.startswith('['):
        try:
            return bytes(ast.literal_eval(stripped))
        except (ValueError, SyntaxError):
            pass
    # Fallback: raw bytes
    return stripped.encode('utf-8')


def write_output(output_data: str, output_file: Optional[str] = None) -> None:
    """Write output to file or stdout."""
    if output_file:
        try:
            Path(output_file).write_text(output_data, encoding='utf-8')
            logger.info("Output written to %s", output_file)
        except OSError as e:
            logger.error("Error writing output file: %s", e)
            print(output_data)
    else:
        print(output_data)


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load config.json if present."""
    p = Path(config_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load config %s: %s", config_path, e)
        return {}


# ----------------------------------------------------------------------------- 
# Batch processing
# -----------------------------------------------------------------------------

def process_batch(
    input_dir: str,
    output_dir: str,
    decompiler: LuauDecompiler,
    disassemble: bool = False,
    extensions: Tuple[str, ...] = ('.luac', '.lua', '.bin', '.rbmx', '.rbm'),
) -> List[Tuple[str, str]]:
    """Process all supported files in a directory. Returns list of (file, status)."""
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    results: List[Tuple[str, str]] = []

    for entry in sorted(in_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in extensions:
            continue
        try:
            if entry.suffix.lower() in ('.rbmx', '.rbm'):
                chunks = extract_bytecode_from_rbmx(str(entry))
                for name, bytecode in chunks:
                    result = (decompiler.disassemble(bytecode) if disassemble
                              else decompiler.decompile(bytecode))
                    out_file = out_path / f"{entry.stem}__{name}.lua"
                    out_file.write_text(result, encoding='utf-8')
                results.append((entry.name, f"ok ({len(chunks)} chunks)"))
            else:
                bytecode = entry.read_bytes()
                result = (decompiler.disassemble(bytecode) if disassemble
                          else decompiler.decompile(bytecode))
                out_file = out_path / f"{entry.stem}.lua"
                out_file.write_text(result, encoding='utf-8')
                results.append((entry.name, "ok"))
        except Exception as e:
            results.append((entry.name, f"error: {e}"))
            logger.error("Failed to process %s: %s", entry, e)
    return results


# ----------------------------------------------------------------------------- 
# CLI
# -----------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{__tool_name__} | Done by vortexdq",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python decompiler.py script.luac -f\n"
            "  python decompiler.py script.luac -f -d\n"
            "  python decompiler.py model.rbmx -f\n"
            "  python decompiler.py --batch input_dir output_dir\n"
            "  python decompiler.py --server\n"
            "  python decompiler.py \"b64_encoded_string\"\n"
        ),
    )
    parser.add_argument('input', nargs='?', help='Input bytecode (file, base64, or hex string)')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-f', '--file', action='store_true', help='Treat input as a file path')
    parser.add_argument('-d', '--disassemble', action='store_true', help='Show disassembly instead of source')
    parser.add_argument('--batch', nargs=2, metavar=('INPUT_DIR', 'OUTPUT_DIR'), help='Batch process a directory')
    parser.add_argument('--semicolons', action='store_true', help='Use semicolons in output')
    parser.add_argument('--no-interpolation', action='store_true', help='Disable string interpolation')
    parser.add_argument('--no-upvalue-comments', action='store_true', help='Disable upvalue comments')
    parser.add_argument('--no-line-info', action='store_true', help='Disable original line info')
    parser.add_argument('--no-function-id', action='store_true', help='Disable function ID comments')
    parser.add_argument('--no-loop-steps', action='store_true', help='Disable numeric loop step preservation')
    parser.add_argument('--no-if-expr', action='store_true', help='Disable if expressions')
    parser.add_argument('--no-header', action='store_true', help='Omit decompiler header comment')
    parser.add_argument('--disasm-comments', action='store_true', help='Include disassembly comments in source')
    parser.add_argument('--indent', type=int, default=2, help='Indentation size (default: 2)')
    parser.add_argument('--config', default='config.json', help='Path to config.json')
    parser.add_argument('--server', action='store_true', help='Start HTTP API server')
    parser.add_argument('--port', type=int, default=5000, help='HTTP server port')
    parser.add_argument('--host', default='127.0.0.1', help='HTTP server host (forced to 127.0.0.1 if public)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--version', action='version', version=f"{__tool_name__} v{__version__} (Done by vortexdq)")
    return parser


def main():
    """Main entry point."""
    print(BANNER)
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config file, then override with CLI flags
    config = load_config(args.config)
    config_options = config.get('options', {})

    options = DecompileOptions.from_dict(config_options)
    # CLI overrides
    if args.semicolons: options.semicolons = True
    if args.no_interpolation: options.string_interpolation = False
    if args.no_upvalue_comments: options.comments_for_upvalues = False
    if args.no_line_info: options.original_line_info = False
    if args.no_function_id: options.function_id = False
    if args.no_loop_steps: options.preserve_numeric_loop_steps = False
    if args.no_if_expr: options.use_if_expressions = False
    if args.no_header: options.include_header = False
    if args.disasm_comments: options.include_disassembly_comments = True
    if args.indent: options.indent_size = args.indent

    decompiler = LuauDecompiler(options)

    # Server mode
    if args.server:
        if not FLASK_AVAILABLE:
            logger.error("Flask is not installed. Install with: pip install flask")
            sys.exit(1)
        server = DecompilerServer(decompiler, options)
        try:
            server.run(host=args.host, port=args.port)
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        return

    # Batch mode
    if args.batch:
        results = process_batch(args.batch[0], args.batch[1], decompiler,
                                disassemble=args.disassemble)
        print("\nBatch results:")
        for name, status in results:
            print(f"  {name}: {status}")
        return

    # Single input
    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        # Handle .rbmx/.rbm files specially
        if args.file and args.input.lower().endswith(('.rbmx', '.rbm')):
            chunks = extract_bytecode_from_rbmx(args.input)
            print(f"Found {len(chunks)} bytecode chunk(s) in {args.input}\n")
            for name, bytecode in chunks:
                print(f"-- Chunk: {name} " + "-" * 40)
                if args.disassemble:
                    result = decompiler.disassemble(bytecode)
                else:
                    result = decompiler.decompile(bytecode)
                if args.output:
                    out_path = Path(args.output)
                    if len(chunks) > 1:
                        out_path = out_path.with_name(f"{out_path.stem}__{name}{out_path.suffix}")
                    out_path.write_text(result, encoding='utf-8')
                    logger.info("Wrote %s", out_path)
                else:
                    print(result)
            return

        bytecode = process_input(args.input, args.file)
        if args.disassemble:
            result = decompiler.disassemble(bytecode)
        else:
            result = decompiler.decompile(bytecode)
        write_output(result, args.output)
    except DecompileError as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == '__main__':
    main()