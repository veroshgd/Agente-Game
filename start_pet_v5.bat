@echo off
rem Starts (or continues) a separate pet on rules v5.
rem The first run creates pet/data/v5-demo.json on v5; later runs continue that same pet.
rem Your original pet in pet/data/pet.json is not touched and keeps its own rules.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 run_pet.py --save pet/data/v5-demo.json --new-rules 5
) else (
  python run_pet.py --save pet/data/v5-demo.json --new-rules 5
)
pause
