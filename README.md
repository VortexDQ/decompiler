
> **Done by vortexdq**
> Version 2.0.0

A local, safe tool for decompiling Roblox Luau bytecode to readable source code.
Runs 100% on your machine. No telemetry, no remote servers, no shady network calls.

---

## ✨ Features

- **Decompile** Luau bytecode to readable Luau source code
- **Disassemble** bytecode for low-level inspection
- **HTTP API** for programmatic use (localhost only — never exposed publicly)
- **Multiple input formats**: raw `.luac`, base64, hex, Python byte-list
- **`.rbmx` / `.rbm` support** — extract and decompile embedded bytecode from Roblox XML model files
- **Batch processing** — decompile an entire folder at once
- **Configurable formatting** via `config.json` or CLI flags
- **Robust error handling** — specific exceptions, no bare `except:` clauses
- **Safety-first** — refuses to bind to public interfaces, uses `ast.literal_eval` (not `eval`)
- **Clean launchers** for Windows (`.bat`) and Unix (`.sh`)

---

## 📦 Installation

1. Install **Python 3.7+** from <https://www.python.org/>
2. Install dependencies (only needed for the HTTP server / client):

   ```bash
   pip install -r requirements.txt
   ```

> **Note:** CLI decompilation works with zero dependencies. Flask is only required for `--server` mode, and `requests` is only required for `client.py`.

---

## 🚀 Quick Start

### Decompile a file

```bash
# Windows
start_decompiler.bat decompile script.luac

# Unix
./start_decompiler.sh decompile script.luac
```

### Decompile a Roblox model (`.rbmx` / `.rbm`)

```bash
start_decompiler.bat decompile model.rbmx -o output.lua
```

### Disassemble (low-level view)

```bash
start_decompiler.bat disassemble script.luac
```

### Batch process a folder

```bash
start_decompiler.bat batch input_folder output_folder
```

### Start the HTTP API server

```bash
start_decompiler.bat server
```

Then in another terminal:

```bash
python client.py health
python client.py decompile script.luac -f
```

---

## 🖥️ Command-Line Usage

```
python decompiler.py [input] [options]

Commands:
  input                  Input bytecode (file path, base64, or hex string)
  -f, --file             Treat input as a file path
  -d, --disassemble      Show disassembly instead of decompiled source
  -o, --output FILE      Write output to FILE
  --batch IN OUT         Batch process a directory
  --server               Start HTTP API server
  --port N               HTTP server port (default 5000)
  --host HOST            HTTP server host (forced to 127.0.0.1 if public)
  --config FILE          Path to config.json (default: config.json)
  --indent N             Indentation size (default 2)
  --semicolons           Use semicolons in output
  --no-header            Omit decompiler header comment
  --no-interpolation     Disable string interpolation
  --no-upvalue-comments  Disable upvalue comments
  --no-line-info         Disable original line info
  --no-function-id       Disable function ID comments
  --disasm-comments      Include disassembly comments in source
  --verbose              Enable verbose logging
  --version              Show version
```

### Examples

```bash
# Decompile a .luac file
python decompiler.py script.luac -f

# Decompile and save to file
python decompiler.py script.luac -f -o output.lua

# Disassemble
python decompiler.py script.luac -f -d

# Decompile a .rbmx Roblox model
python decompiler.py model.rbmx -f

# Process base64 input
python decompiler.py "b64_encoded_string"

# Batch process
python decompiler.py --batch input_dir output_dir

# Start server on custom port
python decompiler.py --server --port 8080
```

---

## 🌐 HTTP API

### `GET /health`

Returns server health and metadata.

```json
{
  "status": "ok",
  "tool": "Luau Bytecode Decompiler Tool - 10x Edition",
  "version": "2.0.0",
  "author": "vortexdq"
}
```

### `GET /info`

Returns server info and current options.

### `POST /decompile`

Request body:

```json
{
  "bytecode": "base64_encoded_bytecode",
  "mode": "decompile",
  "options": {
    "semicolons": false,
    "indent_size": 2
  }
}
```

- `mode`: `"decompile"` (default) or `"disassemble"`
- `options`: any subset of `DecompileOptions` fields

Response:

```json
{
  "success": true,
  "result": "-- decompiled source...",
  "mode": "decompile",
  "author": "vortexdq",
  "version": "2.0.0"
}
```

### curl examples

```bash
# Health check
curl http://localhost:5000/health

# Decompile
curl -X POST http://localhost:5000/decompile \
  -H "Content-Type: application/json" \
  -d '{"bytecode":"base64_here", "mode":"decompile"}'

# Disassemble
curl -X POST http://localhost:5000/decompile \
  -H "Content-Type: application/json" \
  -d '{"bytecode":"base64_here", "mode":"disassemble"}'
```

---

## ⚙️ Configuration (`config.json`)

```json
{
  "options": {
    "semicolons": false,
    "string_interpolation": true,
    "comments_for_upvalues": true,
    "original_line_info": true,
    "function_id": true,
    "preserve_numeric_loop_steps": true,
    "use_if_expressions": true,
    "indent_size": 2,
    "include_header": true,
    "include_disassembly_comments": false,
    "safe_mode": true
  },
  "server": {
    "host": "127.0.0.1",
    "port": 5000
  }
}
```

CLI flags override `config.json` values.

---

## 📁 Project Files

| File                       | Description                                  |
| -------------------------- | -------------------------------------------- |
| `decompiler.py`            | Main decompiler (CLI + HTTP server)          |
| `client.py`                | HTTP API client                              |
| `start_decompiler.bat`     | Windows launcher                             |
| `start_decompiler.sh`      | Unix launcher                                |
| `config.json`              | Configuration                                |
| `requirements.txt`         | Python dependencies                          |
| `sample.rbmx`              | Sample Roblox model for testing              |
| `README.md`                | This file                                    |

---

## 🔒 Safety & Security

This tool was reviewed and hardened:

- **No malware** — no file deletion, no credential stealing, no process injection
- **Localhost only** — the HTTP server refuses to bind to `0.0.0.0` or `::`
- **No `eval`/`exec`** of arbitrary input — uses `ast.literal_eval` (literals only)
- **No telemetry** — zero outbound network calls (except your own localhost server)
- **Bounds-checked** bytecode reader — rejects implausible sizes
- **Specific exceptions** — no bare `except:` clauses that swallow errors
- **Safe XML parsing** — uses Python's standard `xml.etree` (no external entities)

---

## 📝 Credits

**Done by vortexdq**

This is a clean, improved, and safe rewrite. All credit goes to **vortexdq**.

---

## ⚠️ Disclaimer

This tool is for educational and interoperability purposes only. Decompile only
scripts you own or have permission to analyze. Respect Roblox's Terms of Service
and the rights of script authors.