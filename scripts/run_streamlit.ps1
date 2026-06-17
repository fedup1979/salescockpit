$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".\.venv\Scripts\streamlit.exe")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\streamlit.exe run sales_cockpit\ui\app.py --server.port 8501 --server.headless true
