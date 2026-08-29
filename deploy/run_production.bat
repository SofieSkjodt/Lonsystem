@echo off
REM Lønsystem – produktions-wrapper. Starter serveren og genstarter den automatisk
REM hvis processen nogensinde stopper (crash, uventet fejl osv.).
REM Køres af Windows Task Scheduler-opgaven "Lonsystem" (se deploy/setup_scheduled_task.ps1).

cd /d C:\Lonsystem\app

:loop
echo %date% %time% - Starter Lønsystem-serveren...
python -m uvicorn main:app --host 0.0.0.0 --port 8001

echo %date% %time% - Serveren stoppede. Genstarter om 5 sekunder...
timeout /t 5 /nobreak >nul
goto loop
