@echo off
setlocal

echo ========================================
echo   Campus Net Auto Login - Build Tool
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.x first.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [WARN] Tsinghua mirror failed, trying default...
    pip install -r requirements.txt
)

:: Install PyInstaller
echo [2/3] Installing PyInstaller...
pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    pip install pyinstaller
)

:: Clean old build
echo [3/3] Building...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
del /q "*.spec" 2>nul

pyinstaller --onefile --windowed --clean --name "campus-net" --add-data "src;src" --hidden-import src.config --hidden-import src.network --hidden-import src.login --hidden-import src.gui --hidden-import pystray --hidden-import pystray._win32 --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import bs4 --hidden-import bs4.builder._lxml --hidden-import lxml --hidden-import lxml.etree --hidden-import psutil --hidden-import requests --hidden-import json --hidden-import queue --hidden-import urllib.parse --hidden-import re --hidden-import random --hidden-import threading --collect-submodules pystray src/main.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   Build successful!
    echo   Output: dist\campus-net.exe
    echo ========================================
    echo.
    echo You can rename it to anything you like.
    echo The app will ask for credentials on first run.
) else (
    echo.
    echo [ERROR] Build failed. Check messages above.
)

pause
