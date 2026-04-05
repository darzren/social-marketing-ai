@echo off
REM Social Marketing AI — Local Poster
REM Run by Task Scheduler at 9:15am daily (15 min after remote agent generates content)
REM Usage: post_pending.bat velocx_nz

set INDUSTRY=%1
if "%INDUSTRY%"=="" set INDUSTRY=velocx_nz

cd /d c:\social-marketing-ai

REM Pull latest content committed by the remote agent
git pull --quiet

REM Post to social platforms
call venv\Scripts\activate.bat
python main.py --industry %INDUSTRY%
