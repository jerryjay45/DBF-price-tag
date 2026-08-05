@echo off
REM =============================================================================
REM build_windows.bat
REM Build Price Tag Printer natively on Windows 10/11
REM Run this directly on a Windows machine that has Python 3.10+ installed.
REM
REM Usage:
REM   build_windows.bat
REM
REM Output:
REM   dist\windows\PriceTagPrinter_Portable\   <- Portable folder
REM   dist\windows\PriceTagPrinter_Setup_v1.0.0.exe   <- Inno Setup installer (if ISCC found)
REM =============================================================================

setlocal enabledelayedexpansion

set "APP_NAME=PriceTagPrinter"
set "APP_VERSION=1.0.0"
set "APP_DISPLAY=Price Tag Printer"
set "PUBLISHER=Merchant Retail"
set "ENTRY_POINT=price_tag_printer.py"

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "BUILD_DIR=%SCRIPT_DIR%\build_win"
set "DIST_DIR=%SCRIPT_DIR%\dist\windows"

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

echo.
echo ============================================
echo   Price Tag Printer - Windows Build
echo ============================================
echo.

REM ── Step 1: Check Python ─────────────────────────────────────────────────
echo [STEP] Checking Python installation
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install Python 3.10+ from python.org and re-run.
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo [OK]    %PYVER% found

REM ── Step 2: Python dependencies ──────────────────────────────────────────
echo.
echo [STEP] Installing Python dependencies
python -m pip install --upgrade pip --quiet
if errorlevel 1 (echo [ERROR] Failed to upgrade pip & exit /b 1)

echo [INFO] Installing PyQt6...
python -m pip install "PyQt6==6.11.0" --quiet
if errorlevel 1 (echo [ERROR] Failed to install PyQt6 & exit /b 1)

echo [INFO] Installing dbfread...
python -m pip install dbfread --quiet
if errorlevel 1 (echo [ERROR] Failed to install dbfread & exit /b 1)

echo [INFO] Installing PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (echo [ERROR] Failed to install PyInstaller & exit /b 1)

echo [OK]    All packages installed

REM ── Step 3: Icon ──────────────────────────────────────────────────────────
echo.
echo [STEP] Checking assets
if not exist "%SCRIPT_DIR%\assets" mkdir "%SCRIPT_DIR%\assets"
set "ICO_PATH=%SCRIPT_DIR%\assets\price_tag_printer.ico"
if not exist "%ICO_PATH%" (
    echo [WARN] assets\price_tag_printer.ico not found - creating placeholder
    python -c "from PIL import Image; img = Image.new('RGBA', (64, 64), (239, 159, 39, 255)); img.save(r'%ICO_PATH%', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64)])" 2>nul
)

REM ── Step 4: PyInstaller spec ──────────────────────────────────────────────
echo.
echo [STEP] Generating PyInstaller spec
set "SPEC_FILE=%BUILD_DIR%\PriceTagPrinter.spec"

> "%SPEC_FILE%" echo # -*- mode: python ; coding: utf-8 -*-
>> "%SPEC_FILE%" echo from PyInstaller.utils.hooks import collect_all, collect_submodules
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo datas    = []
>> "%SPEC_FILE%" echo binaries = []
>> "%SPEC_FILE%" echo hiddenimports = []
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo qt_d, qt_b, qt_i = collect_all('PyQt6')
>> "%SPEC_FILE%" echo datas     += qt_d
>> "%SPEC_FILE%" echo binaries  += qt_b
>> "%SPEC_FILE%" echo hiddenimports += qt_i
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo hiddenimports += [
>> "%SPEC_FILE%" echo     'dbfread',
>> "%SPEC_FILE%" echo     'dbfread.dbf',
>> "%SPEC_FILE%" echo     'dbfread.field_parser',
>> "%SPEC_FILE%" echo     'dbfread.codepage',
>> "%SPEC_FILE%" echo     'dbfread.dbversions',
>> "%SPEC_FILE%" echo     'dbfread.ifiles',
>> "%SPEC_FILE%" echo     'dbfread.memo',
>> "%SPEC_FILE%" echo     'dbfread.record_iterator',
>> "%SPEC_FILE%" echo ]
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo a = Analysis(
>> "%SPEC_FILE%" echo     ['price_tag_printer.py'],
>> "%SPEC_FILE%" echo     pathex=['.'],
>> "%SPEC_FILE%" echo     binaries=binaries,
>> "%SPEC_FILE%" echo     datas=datas,
>> "%SPEC_FILE%" echo     hiddenimports=hiddenimports,
>> "%SPEC_FILE%" echo     hookspath=[],
>> "%SPEC_FILE%" echo     runtime_hooks=[],
>> "%SPEC_FILE%" echo     excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'sqlite3'],
>> "%SPEC_FILE%" echo     noarchive=False,
>> "%SPEC_FILE%" echo )
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo pyz = PYZ(a.pure)
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo exe = EXE(
>> "%SPEC_FILE%" echo     pyz,
>> "%SPEC_FILE%" echo     a.scripts,
>> "%SPEC_FILE%" echo     [],
>> "%SPEC_FILE%" echo     exclude_binaries=True,
>> "%SPEC_FILE%" echo     name='PriceTagPrinter',
>> "%SPEC_FILE%" echo     debug=False,
>> "%SPEC_FILE%" echo     strip=False,
>> "%SPEC_FILE%" echo     upx=True,
>> "%SPEC_FILE%" echo     console=False,
>> "%SPEC_FILE%" echo     icon=r'%ICO_PATH%',
>> "%SPEC_FILE%" echo )
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo coll = COLLECT(
>> "%SPEC_FILE%" echo     exe,
>> "%SPEC_FILE%" echo     a.binaries,
>> "%SPEC_FILE%" echo     a.datas,
>> "%SPEC_FILE%" echo     strip=False,
>> "%SPEC_FILE%" echo     upx=True,
>> "%SPEC_FILE%" echo     upx_exclude=['Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6PrintSupport.dll'],
>> "%SPEC_FILE%" echo     name='PriceTagPrinter',
>> "%SPEC_FILE%" echo )

copy /y "%SPEC_FILE%" "%SCRIPT_DIR%\PriceTagPrinter.spec" >nul
echo [OK]    Spec file created

REM ── Step 5: Run PyInstaller ─────────────────────────────────────────────
echo.
echo [STEP] Running PyInstaller (this takes several minutes)
cd /d "%SCRIPT_DIR%"
python -m PyInstaller --clean --noconfirm PriceTagPrinter.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    exit /b 1
)

del /q "%SCRIPT_DIR%\PriceTagPrinter.spec" 2>nul

if exist "%SCRIPT_DIR%\dist\PriceTagPrinter" (
    if exist "%DIST_DIR%\PriceTagPrinter_Portable" rmdir /s /q "%DIST_DIR%\PriceTagPrinter_Portable"
    move "%SCRIPT_DIR%\dist\PriceTagPrinter" "%DIST_DIR%\PriceTagPrinter_Portable" >nul
    echo [OK]    Portable build - %DIST_DIR%\PriceTagPrinter_Portable\
) else (
    echo [ERROR] PyInstaller failed - dist\PriceTagPrinter not found
    exit /b 1
)

if not exist "%DIST_DIR%\PriceTagPrinter_Portable\assets" mkdir "%DIST_DIR%\PriceTagPrinter_Portable\assets"
xcopy /y /e /i "%SCRIPT_DIR%\assets\*" "%DIST_DIR%\PriceTagPrinter_Portable\assets\" >nul
echo [OK]    Assets copied

REM ── Step 6: Inno Setup installer (optional) ──────────────────────────────
echo.
echo [STEP] Creating Windows installer (optional)
set "PF86=%ProgramFiles(x86)%"
set "PF64=%ProgramFiles%"
set "INNO_EXE="
where ISCC >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%i in ('where ISCC') do set "INNO_EXE=%%i"
) else if exist "%PF86%\Inno Setup 6\ISCC.exe" (
    set "INNO_EXE=%PF86%\Inno Setup 6\ISCC.exe"
) else if exist "%PF64%\Inno Setup 6\ISCC.exe" (
    set "INNO_EXE=%PF64%\Inno Setup 6\ISCC.exe"
)

if defined INNO_EXE (
    set "ISS_FILE=%BUILD_DIR%\installer.iss"
    set "PORTABLE_DIR=%DIST_DIR%\PriceTagPrinter_Portable"
    set "ICO_PORTABLE=%DIST_DIR%\PriceTagPrinter_Portable\assets\price_tag_printer.ico"

    > "!ISS_FILE!" echo [Setup]
    >> "!ISS_FILE!" echo AppName=%APP_DISPLAY%
    >> "!ISS_FILE!" echo AppVersion=%APP_VERSION%
    >> "!ISS_FILE!" echo AppVerName=%APP_DISPLAY% v%APP_VERSION%
    >> "!ISS_FILE!" echo AppPublisher=%PUBLISHER%
    >> "!ISS_FILE!" echo DefaultDirName={autopf}\%APP_NAME%
    >> "!ISS_FILE!" echo DefaultGroupName=%APP_DISPLAY%
    >> "!ISS_FILE!" echo AllowNoIcons=yes
    >> "!ISS_FILE!" echo OutputDir=%DIST_DIR%
    >> "!ISS_FILE!" echo OutputBaseFilename=%APP_NAME%_Setup_v%APP_VERSION%
    >> "!ISS_FILE!" echo SetupIconFile=!ICO_PORTABLE!
    >> "!ISS_FILE!" echo UninstallDisplayIcon={app}\assets\price_tag_printer.ico
    >> "!ISS_FILE!" echo Compression=lzma2/ultra64
    >> "!ISS_FILE!" echo SolidCompression=yes
    >> "!ISS_FILE!" echo WizardStyle=modern
    >> "!ISS_FILE!" echo MinVersion=10.0
    >> "!ISS_FILE!" echo PrivilegesRequired=admin
    >> "!ISS_FILE!" echo.
    >> "!ISS_FILE!" echo [Languages]
    >> "!ISS_FILE!" echo Name: "english"; MessagesFile: "compiler:Default.isl"
    >> "!ISS_FILE!" echo.
    >> "!ISS_FILE!" echo [Tasks]
    >> "!ISS_FILE!" echo Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
    >> "!ISS_FILE!" echo.
    >> "!ISS_FILE!" echo [Files]
    >> "!ISS_FILE!" echo Source: "!PORTABLE_DIR!\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
    >> "!ISS_FILE!" echo.
    >> "!ISS_FILE!" echo [Icons]
    >> "!ISS_FILE!" echo Name: "{group}\%APP_DISPLAY%";           Filename: "{app}\PriceTagPrinter.exe"; IconFilename: "{app}\assets\price_tag_printer.ico"
    >> "!ISS_FILE!" echo Name: "{group}\Uninstall %APP_DISPLAY%"; Filename: "{uninstallexe}"
    >> "!ISS_FILE!" echo Name: "{autodesktop}\%APP_DISPLAY%";     Filename: "{app}\PriceTagPrinter.exe"; IconFilename: "{app}\assets\price_tag_printer.ico"; Tasks: desktopicon
    >> "!ISS_FILE!" echo.
    >> "!ISS_FILE!" echo [Run]
    >> "!ISS_FILE!" echo Filename: "{app}\PriceTagPrinter.exe"; Description: "{cm:LaunchProgram,%APP_DISPLAY%}"; Flags: nowait postinstall skipifsilent

    echo [INFO] Compiling installer...
    "!INNO_EXE!" "!ISS_FILE!"
    set "INSTALLER=%DIST_DIR%\%APP_NAME%_Setup_v%APP_VERSION%.exe"
    if exist "!INSTALLER!" (
        echo [OK]    Installer - !INSTALLER!
    ) else (
        echo [WARN] Installer not found - check %DIST_DIR%
    )
) else (
    echo [WARN] Inno Setup ^(ISCC.exe^) not found - skipping installer.
    echo        Install it from https://jrsoftware.org/isinfo.php to enable this step.
)

REM ── Done ──────────────────────────────────────────────────────────────────
echo.
echo ============================================
echo   BUILD COMPLETE - Price Tag Printer v%APP_VERSION%
echo ============================================
echo.
echo   Portable:  %DIST_DIR%\PriceTagPrinter_Portable\
if exist "%DIST_DIR%\%APP_NAME%_Setup_v%APP_VERSION%.exe" (
    echo   Installer: %DIST_DIR%\%APP_NAME%_Setup_v%APP_VERSION%.exe
)
echo.
echo   NOTE: Replace assets\price_tag_printer.ico with your real icon if needed.
echo         Place STOCK.DBF alongside the EXE or open it via the Browse button.
echo.

endlocal
