@echo off
cd /d "%~dp0"
echo === 수학 과외 자동화 시스템 시작 ===
echo 숙제 제출을 60초마다 자동 확인합니다. 종료하려면 Ctrl+C
echo.
python main.py
pause
