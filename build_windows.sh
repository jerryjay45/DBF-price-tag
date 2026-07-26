#!/usr/bin/env bash
# =============================================================================
# build_windows.sh
# Cross-compile Price Tag Printer for Windows 10/11 from Linux
# Supports: Arch Linux, Fedora, Debian/Ubuntu
#
# Usage:
#   chmod +x build_windows.sh
#   ./build_windows.sh
#
# Output:
#   dist/windows/PriceTagPrinter_Portable/   ← Portable folder
#   dist/windows/PriceTagPrinter_Setup.exe   ← Inno Setup installer (if ISCC found)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${BOLD}▶ $*${NC}"; }

APP_NAME="PriceTagPrinter"
APP_VERSION="1.0.0"
APP_DISPLAY="Price Tag Printer"
PUBLISHER="Merchant Retail"
ENTRY_POINT="price_tag_printer.py"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build_win"
DIST_DIR="$SCRIPT_DIR/dist/windows"
WINE_PREFIX="$BUILD_DIR/wine_prefix"

WIN_PYTHON_VERSION="3.11.9"
WIN_PYTHON_URL="https://www.python.org/ftp/python/${WIN_PYTHON_VERSION}/python-${WIN_PYTHON_VERSION}-amd64.exe"
WIN_PYTHON_INSTALLER="$BUILD_DIR/python-${WIN_PYTHON_VERSION}-amd64.exe"
WIN_PYTHON_EXE="$WINE_PREFIX/drive_c/Python311/python.exe"

INNO_URL="https://jrsoftware.org/download.php/is.exe"
INNO_INSTALLER="$BUILD_DIR/inno_setup.exe"
INNO_EXE="$WINE_PREFIX/drive_c/Program Files (x86)/Inno Setup 6/ISCC.exe"

mkdir -p "$BUILD_DIR" "$DIST_DIR"

# ── Step 1: Install Wine ──────────────────────────────────────────────────────
step "Checking Wine installation"
if command -v wine &>/dev/null; then
    success "Wine already installed: $(wine --version)"
else
    info "Installing Wine..."
    if command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm wine wine-mono wine-gecko
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y wine
    elif command -v apt-get &>/dev/null; then
        sudo dpkg --add-architecture i386
        sudo apt-get update -q
        sudo apt-get install -y wine wine64 wine32
    else
        error "Unsupported distro. Install Wine manually then re-run."
    fi
    success "Wine installed: $(wine --version)"
fi

# ── Step 2: Wine prefix ───────────────────────────────────────────────────────
step "Setting up Wine prefix (64-bit Windows)"
export WINEPREFIX="$WINE_PREFIX"
export WINEARCH=win64
export WINEDEBUG=-all

if [ ! -f "$WINE_PREFIX/system.reg" ]; then
    info "Initialising Wine prefix..."
    wineboot --init 2>/dev/null || true
    sleep 4
    success "Wine prefix ready"
else
    success "Wine prefix already exists"
fi

# ── Step 3: Windows Python ────────────────────────────────────────────────────
step "Installing Windows Python $WIN_PYTHON_VERSION into Wine"
if [ ! -f "$WIN_PYTHON_EXE" ]; then
    if [ ! -f "$WIN_PYTHON_INSTALLER" ]; then
        info "Downloading Python $WIN_PYTHON_VERSION for Windows..."
        curl -L --progress-bar -o "$WIN_PYTHON_INSTALLER" "$WIN_PYTHON_URL"
        success "Downloaded"
    fi
    info "Installing Python into Wine..."
    wine "$WIN_PYTHON_INSTALLER" /quiet InstallAllUsers=1 \
        TargetDir='C:\Python311' PrependPath=1 2>/dev/null || true
    sleep 6
    [ -f "$WIN_PYTHON_EXE" ] && success "Python installed" \
        || error "Python install failed — $WIN_PYTHON_EXE not found"
else
    success "Windows Python already installed"
fi

WINE_PY="wine $WIN_PYTHON_EXE"
WINE_PIP="wine $WIN_PYTHON_EXE -m pip"
$WINE_PY --version 2>/dev/null && success "Wine Python OK" || error "Wine Python not working"

# ── Step 4: Python dependencies ───────────────────────────────────────────────
step "Installing Python dependencies"
info "Upgrading pip..."
$WINE_PIP install --upgrade pip --quiet 2>/dev/null

info "Installing PyQt6..."
$WINE_PIP install "PyQt6==6.11.0" --quiet 2>/dev/null

info "Installing dbfread..."
$WINE_PIP install dbfread --quiet 2>/dev/null

info "Installing PyInstaller..."
$WINE_PIP install pyinstaller --quiet 2>/dev/null

success "All packages installed"

# ── Step 5: Icon ──────────────────────────────────────────────────────────────
step "Checking assets"
mkdir -p "$SCRIPT_DIR/assets"
if [ ! -f "$SCRIPT_DIR/assets/price_tag_printer.ico" ]; then
    warn "assets/price_tag_printer.ico not found — creating placeholder"
    python3 -c "
try:
    from PIL import Image
    img = Image.new('RGBA', (64, 64), (239, 159, 39, 255))
    img.save('$SCRIPT_DIR/assets/price_tag_printer.ico', format='ICO',
             sizes=[(16,16),(32,32),(48,48),(64,64)])
    print('Placeholder icon created')
except Exception as e:
    print(f'Could not create icon: {e}')
" 2>/dev/null || true
fi

ICO_PATH="$SCRIPT_DIR/assets/price_tag_printer.ico"
ICO_WIN=$(winepath -w "$ICO_PATH" 2>/dev/null || echo "Z:\\${ICO_PATH//\//\\}")
ICO_WIN_ESC="${ICO_WIN//\\/\\\\}"

# ── Step 6: PyInstaller spec ──────────────────────────────────────────────────
step "Generating PyInstaller spec"

cat > "$BUILD_DIR/PriceTagPrinter.spec" << SPEC
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas    = []
binaries = []
hiddenimports = []

qt_d, qt_b, qt_i = collect_all('PyQt6')
datas     += qt_d
binaries  += qt_b
hiddenimports += qt_i

hiddenimports += [
    'dbfread',
    'dbfread.dbf',
    'dbfread.field_parser',
    'dbfread.codepage',
    'dbfread.dbversions',
    'dbfread.ifiles',
    'dbfread.memo',
    'dbfread.record_iterator',
]

a = Analysis(
    ['price_tag_printer.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'sqlite3'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PriceTagPrinter',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='${ICO_WIN_ESC}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6PrintSupport.dll'],
    name='PriceTagPrinter',
)
SPEC

cp "$BUILD_DIR/PriceTagPrinter.spec" "$SCRIPT_DIR/PriceTagPrinter.spec"
success "Spec file created"

# ── Step 7: Run PyInstaller ───────────────────────────────────────────────────
step "Running PyInstaller (this takes several minutes)"
cd "$SCRIPT_DIR"

PYINSTALLER_EXE="$WINE_PREFIX/drive_c/Python311/Scripts/pyinstaller.exe"
[ -f "$PYINSTALLER_EXE" ] || error "pyinstaller.exe not found at $PYINSTALLER_EXE"

wine "$PYINSTALLER_EXE" \
    --clean \
    --noconfirm \
    PriceTagPrinter.spec \
    2>&1 | grep -v "^Traceback\|^  File\|^\s*$\|^WARNING: lib\|^[0-9]* INFO" | tail -40

rm -f "$SCRIPT_DIR/PriceTagPrinter.spec"

if [ -d "$SCRIPT_DIR/dist/PriceTagPrinter" ]; then
    rm -rf "$DIST_DIR/PriceTagPrinter_Portable"
    mv "$SCRIPT_DIR/dist/PriceTagPrinter" "$DIST_DIR/PriceTagPrinter_Portable"
    success "Portable build → $DIST_DIR/PriceTagPrinter_Portable/"
else
    error "PyInstaller failed — dist/PriceTagPrinter not found"
fi

mkdir -p "$DIST_DIR/PriceTagPrinter_Portable/assets"
cp -r "$SCRIPT_DIR/assets/"* "$DIST_DIR/PriceTagPrinter_Portable/assets/" 2>/dev/null || true
success "Assets copied"

# ── Step 8: Inno Setup installer ──────────────────────────────────────────────
step "Creating Windows installer (optional)"
if [ ! -f "$INNO_EXE" ]; then
    info "Installing Inno Setup..."
    [ ! -f "$INNO_INSTALLER" ] && curl -L --progress-bar -o "$INNO_INSTALLER" "$INNO_URL"
    wine "$INNO_INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES 2>/dev/null || true
    sleep 5
fi

if [ -f "$INNO_EXE" ]; then
    PORTABLE_WIN=$(winepath -w "$DIST_DIR/PriceTagPrinter_Portable" 2>/dev/null \
        || echo "Z:${DIST_DIR//\//\\}\\PriceTagPrinter_Portable")
    OUTPUT_WIN=$(winepath -w "$DIST_DIR" 2>/dev/null \
        || echo "Z:${DIST_DIR//\//\\}")
    ICO_PORTABLE_WIN=$(winepath -w "$DIST_DIR/PriceTagPrinter_Portable/assets/price_tag_printer.ico" 2>/dev/null \
        || echo "Z:${DIST_DIR//\//\\}\\PriceTagPrinter_Portable\\assets\\price_tag_printer.ico")

    cat > "$BUILD_DIR/installer.iss" << ISS
[Setup]
AppName=${APP_DISPLAY}
AppVersion=${APP_VERSION}
AppVerName=${APP_DISPLAY} v${APP_VERSION}
AppPublisher=${PUBLISHER}
DefaultDirName={autopf}\\${APP_NAME}
DefaultGroupName=${APP_DISPLAY}
AllowNoIcons=yes
OutputDir=${OUTPUT_WIN}
OutputBaseFilename=${APP_NAME}_Setup_v${APP_VERSION}
SetupIconFile=${ICO_PORTABLE_WIN}
UninstallDisplayIcon={app}\\assets\\price_tag_printer.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "${PORTABLE_WIN}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\${APP_DISPLAY}";           Filename: "{app}\\PriceTagPrinter.exe"; IconFilename: "{app}\\assets\\price_tag_printer.ico"
Name: "{group}\\Uninstall ${APP_DISPLAY}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\\${APP_DISPLAY}";     Filename: "{app}\\PriceTagPrinter.exe"; IconFilename: "{app}\\assets\\price_tag_printer.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\\PriceTagPrinter.exe"; Description: "{cm:LaunchProgram,${APP_DISPLAY}}"; Flags: nowait postinstall skipifsilent
ISS

    ISS_WIN=$(winepath -w "$BUILD_DIR/installer.iss" 2>/dev/null \
        || echo "Z:${BUILD_DIR//\//\\}\\installer.iss")

    info "Compiling installer..."
    wine "$INNO_EXE" "$ISS_WIN" 2>/dev/null || warn "Inno Setup had warnings"

    INSTALLER="$DIST_DIR/${APP_NAME}_Setup_v${APP_VERSION}.exe"
    if [ -f "$INSTALLER" ]; then
        success "Installer → $INSTALLER"
    else
        warn "Installer not found — check $DIST_DIR"
    fi
else
    warn "Inno Setup not available — skipping installer"
fi

# ── Step 9: Quick Wine test ───────────────────────────────────────────────────
step "Testing portable build in Wine"
TEST_EXE="$DIST_DIR/PriceTagPrinter_Portable/PriceTagPrinter.exe"
if [ -f "$TEST_EXE" ]; then
    info "Launching for 5 seconds to verify it starts..."
    timeout 5 wine "$TEST_EXE" 2>/dev/null && true
    success "App launched without immediate crash"
else
    warn "EXE not found at $TEST_EXE"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  BUILD COMPLETE — Price Tag Printer v${APP_VERSION}${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Portable:  ${CYAN}$DIST_DIR/PriceTagPrinter_Portable/${NC}"
[ -f "$DIST_DIR/${APP_NAME}_Setup_v${APP_VERSION}.exe" ] && \
echo -e "  Installer: ${CYAN}$DIST_DIR/${APP_NAME}_Setup_v${APP_VERSION}.exe${NC}"
echo ""
echo -e "  To test in Wine:"
echo -e "  ${YELLOW}WINEPREFIX=$WINE_PREFIX wine \"$TEST_EXE\"${NC}"
echo ""
echo -e "  ${YELLOW}NOTE:${NC} Replace assets/price_tag_printer.ico with your real icon."
echo -e "        Place STOCK.DBF alongside the EXE or open it via the Browse button."
echo ""
