\
    REM Setup script for Windows (PowerShell)
    REM Run this from the project root in PowerShell as Administrator (or allow script execution for the session)
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r backend/requirements.txt
    echo "Setup complete. Edit .env (copy .env.example -> .env) and fill API_KEY and other keys."
    echo "Pull your Ollama model: ollama pull deepseek-r1:4b (or llama3:4b-instruct-q4)"
    echo "To run backend: cd backend; .\\.venv\\Scripts\\Activate.ps1; uvicorn main:app --reload --host 0.0.0.0 --port 8000"
