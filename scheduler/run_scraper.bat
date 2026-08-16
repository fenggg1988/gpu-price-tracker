@echo off
cd /d C:\Users\fengz\gpu-price-tracker
call .venv\Scripts\activate.bat 2>nul || python -m venv .venv && call .venv\Scripts\activate.bat
python main.py scrape >> logs\scrape.log 2>&1
echo [%date% %time%] Scrape completed >> logs\scrape.log
