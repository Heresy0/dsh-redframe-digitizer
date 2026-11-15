@echo off
setlocal
cd /d "%~dp0"
if not "%~1"=="" (
  if not exist "%~1" (
    echo The supplied Harness Python path does not exist.
    exit /b 1
  )
  "%~1" "%~dp0setup.py" --getdata-exe "%~2"
  goto :finish
)
if defined DSH_PRIMARY_RUNTIME (
  if exist "%DSH_PRIMARY_RUNTIME%\dependencies\python\python.exe" (
    "%DSH_PRIMARY_RUNTIME%\dependencies\python\python.exe" "%~dp0setup.py" --getdata-exe "%REDFRAME_GETDATA_EXE%"
    goto :finish
  )
)
echo In DeepSeek Harness, call load_workspace_dependencies to obtain its Python path.
echo Then run: install.cmd "FULL_PATH_TO_HARNESS_PYTHON_EXE" "FULL_PATH_TO_GETDATA_EXE"
echo Or run that Python executable with this folder's setup.py.
pause
exit /b 1
:finish
exit /b %errorlevel%
