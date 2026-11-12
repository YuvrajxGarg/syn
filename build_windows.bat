@echo off
REM Builds dist\Syn\Syn.exe (ffmpeg bundled). Run on Windows with Python 3.9+ installed.
cd /d "%~dp0"
py -3 -m venv .venv-build || python -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install pyinstaller certifi -r requirements.txt
if exist premiere\build_ccx.py (
  set /p SYNVER=<VERSION
  call python premiere\build_ccx.py --version %%SYNVER%%
)
pyinstaller --noconfirm --log-level WARN Syn.spec
echo.
echo Done: dist\Syn\Syn.exe
pause
