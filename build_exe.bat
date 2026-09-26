@echo off
title SingerPro - Build Windows Executable (.exe)
echo ====================================================
echo Building SingerPro Standalone Windows Executable
echo ====================================================

python -m PyInstaller --noconfirm --onedir --windowed ^
    --name "SingerPro" ^
    --collect-data customtkinter ^
    --collect-all sounddevice ^
    --collect-all scipy ^
    --collect-all numba ^
    --hidden-import "scipy.signal" ^
    --hidden-import "customtkinter" ^
    --hidden-import "sounddevice" ^
    main.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo ====================================================
    echo Build Successful! Executable is located at:
    echo dist\SingerPro\SingerPro.exe
    echo ====================================================
) else (
    echo Build failed with error code %ERRORLEVEL%.
)
pause
