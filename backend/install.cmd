@echo off
setlocal
cd /d "%~dp0"
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "%~dp0setup.py" %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3.12 x64 was not found. Install Python 3.12 x64 or initialize Codex local runtime, then try again.
    pause
    exit /b 1
  )
  py -3.12 "%~dp0setup.py" %*
)
set "REDFRAME_RESULT=%errorlevel%"
if not "%REDFRAME_RESULT%"=="0" echo Setup failed. Read the message above or see START_HERE.md.
pause
exit /b %REDFRAME_RESULT%
