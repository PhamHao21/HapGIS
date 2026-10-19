@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo HAPGIS v1.2 - BUILD RELEASE
echo ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay .venv\Scripts\python.exe
    echo Hay chay lenh: py -m venv .venv
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

python -m pip install pyinstaller
if errorlevel 1 goto :fail

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name HAPGIS ^
  --icon "assets\hapgis.ico" ^
  --version-file "version_info.txt" ^
  --add-data "assets\hapgis.ico;assets" ^
  --collect-all customtkinter ^
  --collect-all geopandas ^
  --collect-all pyogrio ^
  --collect-all shapely ^
  --collect-all pyproj ^
  app_gui.py

if errorlevel 1 goto :fail

copy /Y "README.txt" "dist\HAPGIS\README.txt" >nul
copy /Y "RELEASE_NOTES.txt" "dist\HAPGIS\RELEASE_NOTES.txt" >nul

echo.
echo ============================================================
echo BUILD THANH CONG
echo File chay: dist\HAPGIS\HAPGIS.exe
echo Hay test EXE truoc khi nen ZIP.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo ============================================================
echo BUILD THAT BAI - xem loi o tren.
echo ============================================================
pause
exit /b 1
