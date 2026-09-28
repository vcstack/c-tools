@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements-desktop.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --name CtoolTTS --paths . ^
  --collect-all PySide6 tts_studio.py
echo.
echo EXE: dist\CtoolTTS\CtoolTTS.exe
pause
