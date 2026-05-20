@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: ─────────────────────────────────────────────────────────────────────────────
:: MailShield – Windows EXE Builder
:: Run this AFTER install.bat (needs the .venv to already exist)
:: Output: dist\MailShield\MailShield.exe
:: ─────────────────────────────────────────────────────────────────────────────

title MailShield – EXE Builder

echo.
echo  ============================================
echo   MailShield  --  EXE Builder
echo   Powered by PyInstaller
echo  ============================================
echo.

:: ── Check virtual environment ────────────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Run install.bat first, then re-run this script.
    echo.
    pause
    exit /b 1
)

echo [INFO]  Activating virtual environment ...
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Could not activate .venv
    pause
    exit /b 1
)
echo [OK]    Environment active
echo.

:: ── Install / upgrade PyInstaller ────────────────────────────────────────────
echo [INFO]  Installing PyInstaller ...
pip install "pyinstaller>=6.0" --quiet
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller installation failed.
    pause
    exit /b 1
)
echo [OK]    PyInstaller ready
echo.

:: ── Optional: install UPX for smaller binary ─────────────────────────────────
:: UPX compresses the exe; skip silently if not available
where upx >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO]  UPX found – binary will be compressed
) else (
    echo [INFO]  UPX not found – skipping compression (output will be slightly larger)
    echo         Get UPX from https://github.com/upx/upx/releases if you want smaller files
)
echo.

:: ── Clean previous build ─────────────────────────────────────────────────────
echo [INFO]  Cleaning previous build artefacts ...
if exist build\   rmdir /s /q build
if exist dist\    rmdir /s /q dist
echo [OK]    Clean
echo.

:: ── Run PyInstaller ──────────────────────────────────────────────────────────
echo [INFO]  Building MailShield.exe ...
echo         (This usually takes 1-3 minutes – please wait)
echo.

pyinstaller mailshield.spec ^
    --noconfirm ^
    --clean

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    echo         Check the output above for details.
    echo         Common fixes:
    echo           - Make sure all source .py files are in this folder
    echo           - Run:  pip install PyQt5 PyQtWebEngine pycryptodome bcrypt
    echo           - Delete build\ and dist\ then try again
    echo.
    pause
    exit /b 1
)

:: ── Verify output ─────────────────────────────────────────────────────────────
if not exist "dist\MailShield\MailShield.exe" (
    echo [ERROR] Build reported success but MailShield.exe was not found.
    echo         Check dist\ folder manually.
    pause
    exit /b 1
)

:: ── Get file size ─────────────────────────────────────────────────────────────
for /f "tokens=3" %%s in ('dir /a "dist\MailShield\MailShield.exe" ^| findstr "MailShield.exe"') do set EXE_SIZE=%%s
echo.
echo [OK]    Build complete!
echo         dist\MailShield\MailShield.exe  (%EXE_SIZE% bytes)
echo.

:: ── Create desktop shortcut to the exe ───────────────────────────────────────
echo [INFO]  Creating desktop shortcut to MailShield.exe ...
set EXE_PATH=%~dp0dist\MailShield\MailShield.exe
set SHORTCUT=%USERPROFILE%\Desktop\MailShield.lnk

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%~dp0dist\MailShield'; $s.Description = 'MailShield – Secure Email Client'; $s.Save()" ^
  >nul 2>&1

if exist "%SHORTCUT%" (
    echo [OK]    Desktop shortcut created
) else (
    echo [WARN]  Could not create shortcut – launch from dist\MailShield\MailShield.exe
)

:: ── Optional ZIP for distribution ────────────────────────────────────────────
echo.
echo [INFO]  Creating distributable ZIP ...
set ZIP_NAME=MailShield-Windows.zip
if exist "%ZIP_NAME%" del /q "%ZIP_NAME%"

powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\MailShield' -DestinationPath '%ZIP_NAME%'" ^
  >nul 2>&1

if exist "%ZIP_NAME%" (
    echo [OK]    %ZIP_NAME% ready for distribution
) else (
    echo [WARN]  ZIP creation failed – distribute the dist\MailShield\ folder instead
)

:: ── Summary ───────────────────────────────────────────────────────────────────
echo.
echo  ============================================
echo   Build finished successfully
echo  ============================================
echo.
echo   Executable :  dist\MailShield\MailShield.exe
echo   Portable ZIP:  %ZIP_NAME%
echo   Desktop     :  MailShield shortcut
echo.
echo   To distribute MailShield, share the entire
echo   dist\MailShield\ folder  OR  the ZIP file.
echo   The EXE alone will NOT work outside that folder.
echo.
pause
exit /b 0
