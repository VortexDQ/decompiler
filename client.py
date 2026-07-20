#!/usr/bin/env python3
"""
================================================================================
 Luau Bytecode Decompiler - HTTP API Client
 Done by vortexdq
================================================================================
A command-line client for the Luau Decompiler HTTP API.

Features:
  - Send .luac / base64 / hex / .rbmx files to the decompiler server
  - Decompile or disassemble mode
  - Save output to file
  - Health check & server info
  - Verbose error reporting

Author: vortexdq
================================================================================
"""

import sys
import os
import base64
import binascii
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

__version__ = "2.0.0"
__author__ = "vortexdq"
__tool_name__ = "Luau Decompiler Client - 10x Edition"

BANNER = f"""
==============================================================================
 {__tool_name__}
 Version {__version__}  |  Done by vortexdq
==============================================================================
"""


def encode_bytecode_file(path: str) -> str:
    """Read a file and return its base64-encoded contents."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    data = p.read_bytes()
    return base64.b64encode(data).decode('ascii')


def encode_bytecode_string(text: str) -> str:
    """Encode a base64/hex/raw string input to base64 for the API."""
    stripped = text.strip()
    # Already base64?
    try:
        base64.b64decode(stripped, validate=True)
        return stripped
    except (binascii.Error, ValueError):
        pass
    # Hex with 0x
    if stripped.lower().startswith('0x'):
        try:
            raw = bytes.fromhex(stripped[2:])
            return base64.b64encode(raw).decode('ascii')
        except ValueError:
            pass
    # Plain hex
    if len(stripped) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in stripped):
        try:
            raw = bytes.fromhex(stripped)
            return base64.b64encode(raw).decode('ascii')
        except ValueError:
            pass
    # Raw text -> bytes -> base64
    return base64.b64encode(stripped.encode('utf-8')).decode('ascii')


def api_call(host: str, port: int, endpoint: str, method: str = 'GET',
             payload: Optional[Dict[str, Any]] = None,
             timeout: float = 30.0) -> Dict[str, Any]:
    """Perform an API call and return parsed JSON."""
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("requests library not installed. Run: pip install requests")
    url = f"http://{host}:{port}{endpoint}"
    try:
        if method == 'GET':
            resp = requests.get(url, timeout=timeout)
        else:
            resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot connect to server at {host}:{port}. Is it running?")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request to {url} timed out after {timeout}s")
    except requests.exceptions.HTTPError as e:
        try:
            return e.response.json()
        except (ValueError, json.JSONDecodeError):
            raise RuntimeError(f"HTTP error {e.response.status_code}: {e.response.text}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Request error: {e}")


def cmd_health(host: str, port: int) -> int:
    """Check server health."""
    try:
        data = api_call(host, port, '/health')
        print(f"Status:   {data.get('status')}")
        print(f"Tool:     {data.get('tool')}")
        print(f"Version:  {data.get('version')}")
        print(f"Author:   {data.get('author')}")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_info(host: str, port: int) -> int:
    """Show server info."""
    try:
        data = api_call(host, port, '/info')
        print(json.dumps(data, indent=2))
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_decompile(host: str, port: int, input_data: str, is_file: bool,
                  mode: str, output: Optional[str], options: Optional[Dict[str, Any]]) -> int:
    """Send bytecode to the decompiler API."""
    try:
        if is_file:
            encoded = encode_bytecode_file(input_data)
        else:
            encoded = encode_bytecode_string(input_data)
    except (FileNotFoundError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    payload = {
        'bytecode': encoded,
        'mode': mode,
    }
    if options:
        payload['options'] = options

    try:
        data = api_call(host, port, '/decompile', method='POST', payload=payload)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not data.get('success'):
        print(f"API error: {data.get('error', 'Unknown error')}", file=sys.stderr)
        return 1

    result = data.get('result', '')
    if output:
        try:
            Path(output).write_text(result, encoding='utf-8')
            print(f"Output written to {output}")
        except OSError as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            print(result)
    else:
        print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{__tool_name__} | Done by vortexdq",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python client.py health\n"
            "  python client.py info\n"
            "  python client.py decompile script.luac -f\n"
            "  python client.py decompile script.luac -f --mode disassemble\n"
            "  python client.py decompile \"b64string\" -o out.lua\n"
        ),
    )
    parser.add_argument('--host', default='127.0.0.1', help='Server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Server port (default: 5000)')
    parser.add_argument('--version', action='version',
                        version=f"{__tool_name__} v{__version__} (Done by vortexdq)")

    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('health', help='Check server health')
    sub.add_parser('info', help='Show server info')

    dec = sub.add_parser('decompile', help='Decompile or disassemble bytecode')
    dec.add_argument('input', help='Input file path or base64/hex string')
    dec.add_argument('-f', '--file', action='store_true', help='Treat input as a file path')
    dec.add_argument('--mode', choices=['decompile', 'disassemble'], default='decompile',
                     help='Operation mode (default: decompile)')
    dec.add_argument('-o', '--output', help='Write result to file instead of stdout')
    dec.add_argument('--semicolons', action='store_true', help='Use semicolons in output')
    dec.add_argument('--no-interpolation', action='store_true', help='Disable string interpolation')
    dec.add_argument('--no-upvalue-comments', action='store_true', help='Disable upvalue comments')
    dec.add_argument('--no-line-info', action='store_true', help='Disable original line info')
    dec.add_argument('--no-function-id', action='store_true', help='Disable function ID comments')
    dec.add_argument('--indent', type=int, default=None, help='Indentation size')

    return parser


def main() -> int:
    print(BANNER)
    parser = build_parser()
    args = parser.parse_args()

    if args.command == 'health':
        return cmd_health(args.host, args.port)
    if args.command == 'info':
        return cmd_info(args.host, args.port)
    if args.command == 'decompile':
        options: Dict[str, Any] = {}
        if args.semicolons: options['semicolons'] = True
        if args.no_interpolation: options['string_interpolation'] = False
        if args.no_upvalue_comments: options['comments_for_upvalues'] = False
        if args.no_line_info: options['original_line_info'] = False
        if args.no_function_id: options['function_id'] = False
        if args.indent is not None: options['indent_size'] = args.indent
        return cmd_decompile(args.host, args.port, args.input, args.file,
                             args.mode, args.output, options or None)
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())