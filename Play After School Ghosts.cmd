@echo off
rem Double-click this file to play After School Ghosts (English).
if not exist "%~dp0launcher\launch.ps1" goto missing
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0launcher\launch.ps1" %*
exit /b

:missing
echo.
echo  The launcher files were not found next to this file.
echo.
echo  If you opened this from inside the zip, close it, right-click the zip,
echo  choose "Extract All...", and run "Play After School Ghosts" from the
echo  extracted folder.
echo.
pause
