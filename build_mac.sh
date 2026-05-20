#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MailShield – macOS App Builder
# Produces: dist/MailShield.app  (double-clickable)
#           dist/MailShield.dmg  (drag-to-Applications installer)
#
# Requirements: macOS 12+, Python 3.9-3.12, Homebrew
# Run AFTER install.sh  (needs .venv to already exist)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }

echo -e "${CYAN}"
cat << 'BANNER'
  __  __       _ _ ____  _     _      _     _
 |  \/  | __ _(_) / ___|| |__ (_) ___| | __| |
 | |\/| |/ _` | | \___ \| '_ \| |/ _ \ |/ _` |
 | |  | | (_| | | |___) | | | | |  __/ | (_| |
 |_|  |_|\__,_|_|_|____/|_| |_|_|\___|_|\__,_|
BANNER
echo -e "${NC}"
echo "  macOS App Builder  –  .app + .dmg"
echo "  ======================================"
echo ""

# ── Sanity checks ─────────────────────────────────────────────────────────────
section "Checking environment"

[[ "$(uname -s)" == "Darwin" ]] || die "This script must run on macOS."

[[ -f "venv/bin/activate" ]] || \
    die "Virtual environment not found.\nRun ./install.sh first, then re-run this script."

source venv/bin/activate
ok "Virtual environment activated"

python --version | grep -qE "3\.(9|10|11|12)" || \
    warn "Unexpected Python version – build may still work"

# ── PyInstaller ───────────────────────────────────────────────────────────────
section "Installing / upgrading PyInstaller"
python -m pip install --upgrade pip --quiet
echo "Using existing PyInstaller..."
ok "PyInstaller $(pyinstaller --version)"
# ── Clean ─────────────────────────────────────────────────────────────────────
section "Cleaning previous build"
rm -rf build dist
ok "Clean"

# ── Build .app ────────────────────────────────────────────────────────────────
section "Building MailShield.app"
info "This usually takes 2-4 minutes – please wait…"

# Resolve certifi CA bundle path inside the venv
CERTIFI_WHERE=$(python -c "import certifi; print(certifi.where())")
CERTIFI_DIR=$(dirname "$CERTIFI_WHERE")

# Icon path (use .icns on macOS; falls back gracefully if missing)
ICON_ARG=""
if [[ -f "assets/icon.icns" ]]; then
    ICON_ARG="--icon=assets/icon.icns"
    info "Using icon: assets/icon.icns"
elif [[ -f "assets/icon.png" ]]; then
    # Convert PNG → ICNS on the fly using sips + iconutil
    info "Converting assets/icon.png → assets/icon.icns …"
    _ICONSET="assets/icon.iconset"
    mkdir -p "$_ICONSET"
    for _SZ in 16 32 64 128 256 512; do
        sips -z $_SZ $_SZ assets/icon.png --out "$_ICONSET/icon_${_SZ}x${_SZ}.png"     &>/dev/null
        sips -z $((_SZ*2)) $((_SZ*2)) assets/icon.png --out "$_ICONSET/icon_${_SZ}x${_SZ}@2x.png" &>/dev/null
    done
    iconutil -c icns "$_ICONSET" -o assets/icon.icns 2>/dev/null && \
        ICON_ARG="--icon=assets/icon.icns" && ok "Icon converted" || \
        warn "Icon conversion failed – app will use default icon"
    rm -rf "$_ICONSET"
fi

pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "MailShield" \
    --osx-bundle-identifier "com.mailshield.app" \
    $ICON_ARG \
    --add-data "$CERTIFI_WHERE:certifi" \
    $([ -d assets ] && echo "--add-data assets:assets" || true) \
    --hidden-import "PyQt5.QtCore" \
    --hidden-import "PyQt5.QtGui" \
    --hidden-import "PyQt5.QtWidgets" \
    --hidden-import "PyQt5.QtSvg" \
    --hidden-import "PyQt5.QtWebEngineWidgets" \
    --hidden-import "PyQt5.QtWebEngineCore" \
    --hidden-import "PyQt5.QtWebChannel" \
    --hidden-import "PyQt5.QtNetwork" \
    --hidden-import "PyQt5.QtPrintSupport" \
    --hidden-import "PyQt5.sip" \
    --hidden-import "Crypto.Cipher.AES" \
    --hidden-import "Crypto.Random" \
    --hidden-import "email.mime.multipart" \
    --hidden-import "email.mime.text" \
    --hidden-import "email.mime.base" \
    --hidden-import "email.encoders" \
    --hidden-import "chardet.universaldetector" \
    --hidden-import "bs4.builder._htmlparser" \
    --exclude-module "tkinter" \
    --exclude-module "matplotlib" \
    --exclude-module "numpy" \
    --exclude-module "pandas" \
    --exclude-module "pytest" \
    --exclude-module "IPython" \
    main.py

APP="dist/MailShield.app"
[[ -d "$APP" ]] || die "Build failed – MailShield.app not found in dist/"
ok "MailShield.app built"

# ── Patch Info.plist ──────────────────────────────────────────────────────────
section "Patching Info.plist"
PLIST="$APP/Contents/Info.plist"

# Inject high-resolution + dark-mode support keys if not already present
/usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true"       "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true"  "$PLIST"

/usr/libexec/PlistBuddy -c "Set :NSRequiresAquaSystemAppearance false"       "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :NSRequiresAquaSystemAppearance bool false"  "$PLIST"

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0"       "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.0.0" "$PLIST"

/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 1.0.0"       "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 1.0.0" "$PLIST"

/usr/libexec/PlistBuddy -c "Set :NSHumanReadableCopyright Copyright © 2025 MailShield" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string 'Copyright © 2025 MailShield'" "$PLIST"

ok "Info.plist updated"

# ── Remove macOS quarantine flag ───────────────────────────────────────────────
section "Removing quarantine attribute"
xattr -cr "$APP" 2>/dev/null && ok "Quarantine cleared" || warn "Could not clear quarantine"

# ── Ad-hoc code signing (allows running without an Apple Developer account) ───
section "Code signing (ad-hoc)"
if command -v codesign &>/dev/null; then
    codesign --force --deep --sign - "$APP" 2>/dev/null && \
        ok "Ad-hoc signature applied" || \
        warn "Code signing failed – app may show a Gatekeeper warning on first run"
else
    warn "codesign not found – skipping"
fi

# ── Build .dmg ────────────────────────────────────────────────────────────────
section "Building MailShield.dmg"
DMG="dist/MailShield.dmg"
DMG_TMP="dist/MailShield_tmp.dmg"
DMG_VOLNAME="MailShield"
DMG_SIZE="512m"

rm -f "$DMG" "$DMG_TMP"

# Staging folder for DMG contents
STAGE="dist/_dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
# Add a symlink to /Applications so the user can drag-and-drop
ln -s /Applications "$STAGE/Applications"

# Create DMG
hdiutil create \
    -volname "$DMG_VOLNAME" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "$DMG" \
    &>/dev/null

rm -rf "$STAGE"

if [[ -f "$DMG" ]]; then
    DMG_MB=$(( $(stat -f%z "$DMG") / 1048576 ))
    ok "MailShield.dmg created (${DMG_MB} MB)"
else
    warn "DMG creation failed – distribute dist/MailShield.app directly"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
APP_MB=$(du -sm "$APP" 2>/dev/null | cut -f1)
echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓  macOS build complete!${NC}"
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo ""
echo "  App bundle : dist/MailShield.app  (${APP_MB} MB)"
[[ -f "$DMG" ]] && echo "  Installer  : dist/MailShield.dmg  (${DMG_MB} MB)"
echo ""
echo "  To run now:"
echo -e "    ${CYAN}open dist/MailShield.app${NC}"
echo ""
echo "  To install:"
echo -e "    ${CYAN}open dist/MailShield.dmg${NC}  then drag MailShield → Applications"
echo ""
echo "  First launch Gatekeeper warning?"
echo -e "    ${CYAN}Right-click the app → Open → Open${NC}"
echo -e "    (only needed once)"
echo ""
