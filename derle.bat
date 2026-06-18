@echo off
echo Derleme basliyor...
python -m PyInstaller --onefile --noconsole --add-data "logo.png;." "Fixoria AI.py"
echo.
echo Derleme bitti!
pause