@echo off
title SingerPro - Live Vocal Monitoring
echo Starting SingerPro Studio...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application stopped with an error or Python is not in PATH.
    pause
)
