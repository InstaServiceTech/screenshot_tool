@echo off
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
cd app
echo Open http://127.0.0.1:5000
python app.py
