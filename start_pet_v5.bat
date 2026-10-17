@echo off
rem Starts (or continues) a separate pet on the newest rules (v5).
rem The first run creates pet/data/v5-demo.json; later runs continue that same pet.
rem Your original pet in pet/data/pet.json is not touched and keeps its own rules.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 run_pet.py --save pet/data/v5-demo.json
) else (
  python run_pet.py --save pet/data/v5-demo.json
)
pause
