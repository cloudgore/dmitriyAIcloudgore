@echo off
cd /d "%~dp0"
echo Enable Jarvis at Windows sign-in for this user?
choice /C YN
if errorlevel 2 exit /b
".venv\Scripts\python.exe" manage.py enable
pause
