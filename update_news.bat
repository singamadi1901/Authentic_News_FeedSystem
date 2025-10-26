@echo off
echo [%date% %time%] Starting news update...
call venv\Scripts\activate
python manage.py fetch_and_verify_news
echo [%date% %time%] News update completed!
echo.
echo Waiting 2 hours for next update...
timeout /t 7200 /nobreak
goto :loop
