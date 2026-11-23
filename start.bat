@echo off
setlocal
cd /d "%~dp0"
title CodeHatch

set "PY=.venv\Scripts\python.exe"

if exist "%PY%" goto check_pip

:make_venv
echo [First start] Creating the Python environment...
set "SYSPY="
where py >nul 2>nul && set "SYSPY=py -3"
if not defined SYSPY (
    where python >nul 2>nul && set "SYSPY=python"
)
if not defined SYSPY goto no_python
%SYSPY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto old_python
%SYSPY% -m venv .venv
if errorlevel 1 (
    echo ERROR: Could not create the Python environment.
    pause
    exit /b 1
)

:check_pip
rem A .venv left by a failed first start has no pip: it is made again once
"%PY%" -m pip --version >nul 2>nul
if not errorlevel 1 goto have_venv
if defined VENV_REMADE goto broken_venv
set "VENV_REMADE=1"
echo The Python environment in the .venv folder is incomplete: creating it again...
rmdir /s /q .venv
goto make_venv

:have_venv
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto old_venv

if exist ".env" goto check_env
if exist ".env.example" copy ".env.example" ".env" >nul
echo.
echo The .env file was not found - it was created from the template.
echo Paste your DISCORD_TOKEN into it, save the file and close Notepad.
notepad ".env"

:check_env
findstr /r /c:"^DISCORD_TOKEN=..*" ".env" >nul 2>nul
if errorlevel 1 goto no_token
findstr /c:"DISCORD_TOKEN=your_bot_token_here" ".env" >nul 2>nul
if not errorlevel 1 goto no_token
set "BOT_LAUNCHER=start.bat"

:run
echo Checking libraries...
"%PY%" -m pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 (
    echo ERROR: Could not install the libraries. Check your internet connection.
    echo Still failing? Your Python may be newer than the bot was tested on ^(3.14^): install Python 3.13 or 3.14,
    echo delete the .venv folder and run this file again. Don't keep the bot folder in OneDrive or Dropbox.
    pause
    exit /b 1
)

echo Starting the bot...
"%PY%" main.py
set "CODE=%errorlevel%"

if "%CODE%"=="42" (
    echo Restarting the bot in a few seconds...
    timeout /t 3 /nobreak >nul
    goto run
)
if "%CODE%"=="4" (
    echo.
    echo This bot is already running in another window. Close that window first, or use it.
    pause
    exit /b 4
)
if not "%CODE%"=="0" (
    echo.
    echo The bot stopped with an error ^(code %CODE%^). Details: data\logs\bot.log
    pause
)
exit /b %CODE%

:no_python
echo.
echo ERROR: Python was not found.
echo Install Python 3.12-3.14 from python.org (Windows installer 64-bit), tick "Add python.exe to PATH"
echo and run this file again.
pause
exit /b 1

:old_python
echo.
echo ERROR: The bot needs Python 3.10 or newer, but an older Python was found
echo (or no Python is installed and Windows found only its Microsoft Store shortcut).
echo Install Python from python.org, tick "Add python.exe to PATH" and run this file again.
pause
exit /b 1

:broken_venv
echo.
echo ERROR: The Python environment can't be created with pip.
echo Install Python again from python.org (not from the Microsoft Store), delete the .venv folder and run this file again.
pause
exit /b 1

:old_venv
echo.
echo ERROR: The Python environment in the .venv folder is older than Python 3.10.
echo Install Python 3.12-3.14 from python.org, delete the .venv folder and run this file again.
pause
exit /b 1

:no_token
echo.
echo ERROR: The .env file has no bot token yet (DISCORD_TOKEN).
echo Open .env, paste the token after DISCORD_TOKEN= and save the file. The token is in
echo Discord Developer Portal -^> your app -^> Bot -^> Reset Token.
echo No spaces or quotes: DISCORD_TOKEN=MTI3NDk...
notepad ".env"
echo.
echo Saved the token? Double-click start.bat again to start the bot.
pause
exit /b 1
