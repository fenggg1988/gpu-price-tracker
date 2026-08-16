@echo off
setlocal
set "PROJECT_DIR=C:\Users\fengz\gpu-price-tracker"
set "PYTHON_EXE=C:\Users\fengz\AppData\Local\Programs\Python\Python314\python.exe"
set "LOG_FILE=%PROJECT_DIR%\scrape.log"
cd /d "%PROJECT_DIR%"
echo [%date% %time%] BAT start user=%USERNAME% cwd=%CD% >> "%LOG_FILE%"
"%PYTHON_EXE%" "%PROJECT_DIR%\scrape_gpu_prices.py" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] BAT end exit=%EXIT_CODE% >> "%LOG_FILE%"
exit /b %EXIT_CODE%
