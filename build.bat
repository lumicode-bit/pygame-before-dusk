@echo off
chcp 936 >nul
title 暮色之前 - 一键打包
cd /d "%~dp0"
echo ============================================================
echo   暮色之前 · Before Dusk - 打包（目录模式）
echo ============================================================
echo.

set "PY=C:/Users/clm/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
if exist "%PY%" goto havepy
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)
set "PY=python"

:havepy
echo [1/3] 检查依赖...
"%PY%" -c "import pygame,numpy,PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo       正在安装 pygame / numpy / pyinstaller ...
    "%PY%" -m pip install -r requirements.txt pyinstaller
)

echo [2/3] 打包中（约 1-2 分钟）...
"%PY%" -m PyInstaller ^
    --noconfirm ^
    --windowed ^
    --name "暮色之前" ^
    --icon "game.ico" ^
    --collect-all pygame ^
    --hidden-import game_core ^
    --hidden-import assets ^
    --hidden-import theme ^
    --hidden-import ui ^
    --hidden-import audio ^
    --hidden-import fx ^
    --hidden-import renderer ^
    --hidden-import sprites ^
    --hidden-import numpy ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module scipy ^
    --exclude-module pandas ^
    --exclude-module PIL ^
    main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上面的报错
    pause
    exit /b 1
)

echo.
echo [3/3] 完成：dist\暮色之前\暮色之前.exe
echo.
echo [说明] 用目录模式打包：启动比单文件快，杀毒误报也少。
echo        发给别人时把整个 dist\暮色之前 文件夹压缩后发送，
echo        对方解压后双击里面的 exe 即可，不要只发 exe。
echo.
pause
