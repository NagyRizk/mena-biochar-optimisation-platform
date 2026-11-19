# Start here (Windows)

1. Extract the ZIP to a normal folder (for example `C:\MENA_Biochar_Platform`).
2. Install Python 3.11 from https://www.python.org/downloads/ if it is not already installed. During installation, enable **Add Python to PATH**.
3. Double-click `RUN_PLATFORM.bat`. The first launch creates a virtual environment and installs the dependencies.
4. A browser tab should open at `http://localhost:8501`. If it does not, copy that address into your browser.
5. Use the left sidebar to configure a scenario. Groq is optional; the rest of the platform works without it.
6. To enable Groq, open **AI analyst** in the app and paste a newly rotated API key into the password field. The key is held in the current app session only; it is not saved to the project.

## Important key-security note
A Groq key previously pasted into a chat should be considered exposed. Revoke that key in the Groq console and generate a new one before use. Do not put the new key in this ZIP, notebook, source code, or a public Git repository.

## If the launcher fails
Open PowerShell in this folder and run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks activation, use the `.bat` launcher instead.
