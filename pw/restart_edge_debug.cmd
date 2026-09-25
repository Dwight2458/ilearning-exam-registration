@echo off
rem ============================================================
rem  Fully quit Edge, then relaunch it with a CDP debug port.
rem
rem  Why: Edge keeps background processes alive after you close
rem  all windows (startup boost / background extensions). If any
rem  msedge.exe survives, a new launch just attaches to the
rem  existing process and the --remote-debugging-port flag is
rem  silently ignored.
rem
rem  ASCII only, CRLF, and no "if (...)" blocks: the Edge path
rem  contains "(x86)" which breaks cmd parsing inside blocks.
rem
rem  WARNING: this closes ALL Edge windows. Save any form data
rem  first. Edge will offer to restore your tabs on relaunch.
rem ============================================================

set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if not exist "%EDGE%" goto noedge

echo Closing Edge gracefully...
echo (a graceful close lets Edge persist SSO session cookies; a forced
echo  kill WIPES them and you have to log in to iLearning again)
taskkill /IM msedge.exe >nul 2>&1
ping -n 7 127.0.0.1 >nul

echo Checking for leftover background processes...
tasklist /FI "IMAGENAME eq msedge.exe" 2>nul | find /I "msedge.exe" >nul
if errorlevel 1 goto clean
echo Still running - force closing leftovers...
taskkill /F /IM msedge.exe >nul 2>&1
ping -n 4 127.0.0.1 >nul
goto clean

:clean
echo Edge is fully closed.

echo Starting Edge with debug port 9222...
start "" "%EDGE%" --remote-debugging-port=9222 --remote-allow-origins=*

ping -n 4 127.0.0.1 >nul
echo.
echo Done. Now verify with this command in PowerShell:
echo   curl.exe http://127.0.0.1:9222/json/version
echo If you see JSON, the debug port is live.
echo.
exit /b 0

:noedge
echo [ERROR] Edge not found at the path on line 18.
echo Edit this script and fix the EDGE path.
pause
exit /b 1
