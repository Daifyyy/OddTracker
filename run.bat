@echo off
cd /d "%~dp0"

:: Kill any existing Streamlit on port 8501
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr :8501') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting OddTracker...
streamlit run app.py --server.port 8501
pause
