@echo off
rem Baby Watch: build the app and serve everything on http://localhost:8000 (Windows).
cd /d "%~dp0frontend" || exit /b 1
call npm install || exit /b 1
call npm run build || exit /b 1
cd /d "%~dp0backend" || exit /b 1
pip install -r requirements.txt || exit /b 1
if not exist .env echo Tip: copy .env.example to .env and add your GROQ_API_KEY for AI explanations.
uvicorn app.main:app --port 8000
