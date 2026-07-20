@echo off
REM ============================================================================
REM  Educational Decompiler by
REM  vortexdq
REM ============================================================================
setlocal

echo.
echo ==============================================================================
echo  Educational Decompiler by
echo  | vortexdq
echo ==============================================================================
echo.

REM Prefer python, then py launcher
where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto :run
)
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
    goto :run
)

echo [ERROR] Python was not found on PATH.
echo         Please install Python 3.7+ from https://www.python.org/
exit /b 1

:run
if "%1"=="" (
    echo Usage:
    echo   start_decompiler.bat [command] [options]
    echo.
    echo Commands:
    echo   server                       Start HTTP API server (localhost:5000)
    echo   decompile [file]             Decompile a .luac / .rbmx / .rbm file
    echo   disassemble [file]           Show disassembly of a file
    echo   batch [input_dir] [out_dir]  Batch process a folder
    echo.
    echo Examples:
    echo   start_decompiler.bat server
    echo   start_decompiler.bat decompile script.luac
    echo   start_decompiler.bat decompile model.rbmx -o output.lua
    echo   start_decompiler.bat disassemble script.luac
    echo   start_decompiler.bat batch input_dir output_dir
    echo.
    %PY% decompiler.py --help
    exit /b 1
)

REM Map friendly subcommands to decompiler.py flags
if /I "%1"=="server" (
    shift
    %PY% decompiler.py --server %1 %2 %3 %4 %5
    goto :done
)
if /I "%1"=="decompile" (
    shift
    %PY% decompiler.py %1 -f %2 %3 %4 %5 %6
    goto :done
)
if /I "%1"=="disassemble" (
    shift
    %PY% decompiler.py %1 -f -d %2 %3 %4 %5 %6
    goto :done
)
if /I "%1"=="batch" (
    shift
    %PY% decompiler.py --batch %1 %2 %3 %4 %5
    goto :done
)

REM Unknown command - pass through directly to decompiler.py
%PY% decompiler.py %*

:done
if errorlevel 1 (
    echo.
    echo [!] Command completed with errors.
    pause
)
endlocal