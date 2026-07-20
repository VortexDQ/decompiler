set -e

echo ""
echo "=============================================================================="
echo " Luau Bytecode Decompiler Tool - 10x Edition"
echo "   Partially Made by|  vortexdq for just educational purposes!"
echo "=============================================================================="
echo ""

# Resolve script directory so it works from anywhere
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Find python
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "[ERROR] Python was not found on PATH."
    echo "        Please install Python 3.7+ from https://www.python.org/"
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "Usage:"
    echo "  start_decompiler.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  server                       Start HTTP API server (localhost:5000)"
    echo "  decompile [file]             Decompile a .luac / .rbmx / .rbm file"
    echo "  disassemble [file]           Show disassembly of a file"
    echo "  batch [input_dir] [out_dir]  Batch process a folder"
    echo ""
    echo "Examples:"
    echo "  start_decompiler.sh server"
    echo "  start_decompiler.sh decompile script.luac"
    echo "  start_decompiler.sh decompile model.rbmx -o output.lua"
    echo "  start_decompiler.sh disassemble script.luac"
    echo "  start_decompiler.sh batch input_dir output_dir"
    echo ""
    $PY decompiler.py --help
    exit 1
fi

# Map friendly subcommands to decompiler.py flags
case "$1" in
    server)
        shift
        $PY decompiler.py --server "$@"
        ;;
    decompile)
        shift
        $PY decompiler.py "$1" -f "${@:2}"
        ;;
    disassemble)
        shift
        $PY decompiler.py "$1" -f -d "${@:2}"
        ;;
    batch)
        shift
        $PY decompiler.py --batch "$@"
        ;;
    *)
        # Unknown command - pass through directly to decompiler.py
        $PY decompiler.py "$@"
        ;;
esac