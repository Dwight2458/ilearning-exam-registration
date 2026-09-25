@echo off
rem ============================================================
rem  Start Edge with a CDP debugging port (for cookie refresh).
rem
rem  Keep this file ASCII-only and CRLF: cmd.exe reads .cmd as
rem  ANSI, so UTF-8 Chinese text corrupts the script.
rem  Also do NOT wrap logic in "if (...)" blocks -- the Edge path
rem  contains "(x86)" and that parenthesis breaks cmd parsing.
rem
rem  Steps:
rem    1. Close leftover Welcome tabs (right-click a tab then
rem       "Close other tabs"), or Edge will restore them all.
rem    2. Fully quit Edge (Task Manager: no msedge.exe).
rem    3. Run this script.
rem ============================================================

set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if not exist "%EDGE%" goto noedge

start "" "%EDGE%" --remote-debugging-port=9222 --remote-allow-origins=*

echo.
echo Edge started with debug port 9222.
echo Verify: open http://127.0.0.1:9222/json/version
echo If you see JSON, it works.
echo.
echo SECURITY: the port listens on 127.0.0.1 only, but any local
echo process that can reach it can fully control the browser.
echo To disable, just restart Edge normally.
echo.
exit /b 0

:noedge
echo [ERROR] Edge not found at the path on line 16.
echo Edit this script and fix the EDGE path.
pause
exit /b 1
