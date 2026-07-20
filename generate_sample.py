#!/usr/bin/env python3
"""Generate a sample .rbmx file with embedded Luau bytecode for testing.
Done by vortexdq"""
import base64
import struct
import os

def build_bytecode():
    out = bytearray()
    out += b'LuaU'
    out += bytes([0])
    out += bytes([0] * 16)
    out += bytes([0])
    out += struct.pack('<i', 1)
    out += struct.pack('<i', 10)
    out += bytes([0, 1, 8])
    out += struct.pack('<I', 4)
    out += bytes([5, 0, 0, 0])
    out += bytes([5, 1, 1, 0])
    out += bytes([24, 2, 0, 1])
    out += bytes([48, 2, 2, 0])
    out += struct.pack('<I', 2)
    out += bytes([2]) + struct.pack('<d', 40.0)
    out += bytes([2]) + struct.pack('<d', 2.0)
    out += struct.pack('<I', 0)
    out += struct.pack('<I', 0)
    return bytes(out)

bytecode = build_bytecode()
b64 = base64.b64encode(bytecode).decode('ascii')

rbmx = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<roblox version="4">\n'
    '  <Item class="ModuleScript" name="SampleModule">\n'
    '    <Properties>\n'
    '      <string name="Name">SampleModule</string>\n'
    '      <BinaryString name="Bytecode">' + b64 + '</BinaryString>\n'
    '    </Properties>\n'
    '  </Item>\n'
    '</roblox>\n'
)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample.rbmx')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(rbmx)

print('Generated sample.rbmx (Done by vortexdq)')
print('Bytecode bytes:', len(bytecode), 'base64 chars:', len(b64))
print('Path:', out_path)