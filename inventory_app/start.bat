@echo off
rem ===================================================================
rem  Inventory Manager - one-click start (backend + front end + phone link)
rem
rem  Logins (starting passwords - change them on the Account page):
rem     admin          /  admin
rem     olti kajtazi   /  olti kajtazi    (worker)
rem     lisbytyqi      /  lisbytyqi       (worker)
rem ===================================================================
cd /d "%~dp0"

set "ACT=echo."
if exist "venv\Scripts\activate.bat" set "ACT=call venv\Scripts\activate.bat"

set "CF=cloudflared"
where cloudflared >nul 2>&1 || set "CF=%USERPROFILE%\Downloads\cloudflared-windows-amd64.exe"

start "Inventory backend" cmd /k "%ACT% && python -m uvicorn main:app --reload"
timeout /t 5 /nobreak >nul
start "Inventory front end" cmd /k "%ACT% && python -m streamlit run app.py"
timeout /t 5 /nobreak >nul
start "Inventory tunnel (phone link)" cmd /k ""%CF%" tunnel --url http://localhost:8501"

echo.
echo Three windows opened. Find the https://....trycloudflare.com link in the "tunnel" window
echo and open it on your phone. Close the three windows to stop everything.
echo.
echo Logins:
echo    admin          /  admin
echo    olti kajtazi   /  olti kajtazi   (worker)
echo    lisbytyqi      /  lisbytyqi      (worker)
echo.
pause
