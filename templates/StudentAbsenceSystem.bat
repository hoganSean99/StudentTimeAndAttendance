@echo off
REM Change to the directory containing your app.py
cd /d "D:\Development\Python\TimeAndAttendance"

REM Start the Flask app
start /b python app.py

REM Wait for the server to start and open the browser
timeout /t 3 >nul
start http://127.0.0.1:5000