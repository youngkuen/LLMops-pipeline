@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
python -m streamlit run app/main.py
pause
