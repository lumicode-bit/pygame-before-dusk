@echo off
chcp 936 >nul
title 暮色之前 · Before Dusk
cd /d "%~dp0"

rem ---- 优先使用已装好 pygame 的受管环境 ----
set "PY=C:\Users\clm\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%PY%" goto havepy

rem ---- 否则用系统 Python，缺依赖就装 ----
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH
    pause
    exit /b 1
)
set "PY=python"
"%PY%" -c "import pygame,numpy" >nul 2>nul
if errorlevel 1 (
    echo [提示] 正在安装依赖 pygame / numpy ...
    "%PY%" -m pip install -r requirements.txt
)

:havepy
if "%~1"=="--check" (
    echo [OK] 将使用：%PY%
    "%PY%" -c "import sys,pygame,numpy;print(sys.version.split()[0], 'pygame', pygame.version.ver, 'numpy', numpy.__version__)"
    exit /b 0
)

echo [启动] 暮色之前 · Before Dusk
"%PY%" main.py
if errorlevel 1 (
    echo.
    echo [错误] 游戏异常退出，错误信息见上方
    pause
)
