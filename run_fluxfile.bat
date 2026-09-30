@echo off
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py -3"

if not defined PY_CMD (
  where python >nul 2>&1 && set "PY_CMD=python"
)

if not defined PY_CMD (
  echo FluxFile requires Python 3.10 or newer.
  echo Install Python from python.org and make sure the Python launcher or python.exe is on PATH.
  pause
  exit /b 1
)

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo FluxFile requires Python 3.10 or newer.
  %PY_CMD% --version
  pause
  exit /b 1
)

if exist .venv (
  if not exist .venv\Scripts\python.exe (
    echo FluxFile: incomplete virtual environment detected; rebuilding .venv...
    rmdir /s /q .venv
  )
)

if not exist .venv\Scripts\python.exe (
  echo FluxFile: creating Python virtual environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo FluxFile could not create .venv.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" scripts\bootstrap.py
if errorlevel 1 (
  echo FluxFile dependency setup failed.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" fluxfile.py
set "EXITCODE=%errorlevel%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
