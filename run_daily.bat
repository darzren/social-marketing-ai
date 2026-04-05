@echo off
REM Social Marketing AI — Daily Runner
REM Called by Windows Task Scheduler at 9am

cd /d c:\social-marketing-ai
call venv\Scripts\activate.bat
python main.py --industry generic
