@echo off
REM Lonsystem - produktions-wrapper. Starter serveren og genstarter den automatisk
REM hvis processen nogensinde stopper (crash, uventet fejl osv.).
REM Koeres af Windows Task Scheduler-opgaven "Lonsystem" (se deploy/setup_scheduled_task.ps1).

cd /d C:\Users\LoenPC\Lonsystem\app

:loop
echo %date% %time% - Starter Lonsystem-serveren...
py -m uvicorn main:app --host 0.0.0.0 --port 8000

echo %date% %time% - Serveren stoppede. Genstarter om 5 sekunder...
timeout /t 5 /nobreak >nul
goto loop
