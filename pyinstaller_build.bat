@echo off
chcp 65001 >nul

echo ==========================================
echo        正在打包 Syncplay 为 EXE...
echo ==========================================

call .venv\Scripts\activate

set /p VERSION=<.version

pyinstaller -F -w ^
--name="LAN_Syncplay-%VERSION%" ^
-i assets/byzh16x16-256x256.ico ^
--add-data "assets;assets" ^
--clean ^
--noconfirm ^
main.py

echo.
echo ==========================================
echo           打包完成！文件在 dist 目录
echo ==========================================

pause