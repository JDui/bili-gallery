@echo off
setlocal

cd /d "%~dp0"

echo Running bili_9pics_downloader.py ...
python "%~dp0bili_9pics_downloader.py"
if errorlevel 1 (
    echo.
    echo Failed. Please make sure Python is installed and added to PATH.
    pause
    exit /b %errorlevel%
)

echo.
echo Finished.
pause
