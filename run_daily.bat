@echo off
REM Social Marketing AI — Daily Runner
REM Called by Windows Task Scheduler
REM Usage: run_daily.bat generic
REM        run_daily.bat real_estate

set INDUSTRY=%1
if "%INDUSTRY%"=="" set INDUSTRY=generic

cd /d c:\social-marketing-ai
call venv\Scripts\activate.bat
python main.py --industry %INDUSTRY%
