#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MailShield – Linux / macOS Installer
# Supports: Ubuntu 20.04+, Debian 11+, Fedora 36+, macOS 12+ (Homebrew)
# Python 3.9 – 3.12 required
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
cat << 'BANNER'
  __  __       _ _ ____  _     _      _     _
 |  \/  | __ _(_) / ___|| |__ (_) ___| | __| |
 | |\/| |/ _` | | \___ \| '_ \| |/ _ \ |/ _` |
 | |  | | (_| | | |___) | | | | |  __/ | (_| |
 |_|  |_|\__,_|_|_|____/|_| |_|_|\___|_|\__,_|
BANNER
echo -e "${NC}"
echo "  Secure Email Client  –  Installer"
echo "  ====================================="
echo ""

# ── OS Detection ──────────────────────────────────────────────────────────────
section "Detecting environment"
OS="$(uname -s)"
DISTRO=""
PKG_MGR=""

if [[ "$OS" == "Linux" ]]; then
    if command -v apt-get &>/dev/null; then
        DISTRO="debian"; PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        DISTRO="fedora"; PKG_MGR="dnf"
    elif command -v pacman &>/dev/null; then
        DISTRO="arch"; PKG_MGR="pacman"
    else
        warn "Unknown Linux distro – will skip system-package step"
        DISTRO="unknown"; PKG_MGR="unknown"
    fi
    info "OS: Linux ($DISTRO)"
elif [[ "$OS" == "Darwin" ]]; then
    DISTRO="macos"; PKG_MGR="brew"
    info "OS: macOS"
else
    die "Unsupported OS: $OS"
fi

# ── Python version check ──────────────────────────────────────────────────────
section "Checking Python"
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR="${VER%%.*}"; MINOR="${VER##*.}"
        if [[ "$MAJOR" -eq 3 && "$MINOR" -ge 9 && "$MINOR" -le 12 ]]; then
            PYTHON="$cmd"
            ok "Found $PYTHON (Python $VER)"
            break
        fi
    fi
done
[[ -z "$PYTHON" ]] && die "Python 3.9–3.12 not found. Install it first:\n  Ubuntu: sudo apt install python3\n  macOS:  brew install python@3.11"

# ── System dependencies ───────────────────────────────────────────────────────
section "Installing system dependencies"

if [[ "$PKG_MGR" == "apt" ]]; then
    info "Updating apt and installing packages…"
    sudo apt-get update -qq
    sudo apt-get install -y \
        python3-pip python3-venv \
        python3-pyqt5 python3-pyqt5.qtsvg \
        python3-pyqt5.qtwebengine \
        libgl1-mesa-glx libglib2.0-0 \
        libxcb-xinerama0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-xkb1 libxkbcommon-x11-0 \
        2>/dev/null || warn "Some apt packages may have been skipped (non-fatal)"
    ok "System packages ready"

elif [[ "$PKG_MGR" == "dnf" ]]; then
    info "Installing Fedora packages…"
    sudo dnf install -y \
        python3-pip python3-virtualenv \
        python3-qt5 python3-qt5-base \
        mesa-libGL glib2 \
        2>/dev/null || warn "Some dnf packages may have been skipped (non-fatal)"
    ok "System packages ready"

elif [[ "$PKG_MGR" == "pacman" ]]; then
    info "Installing Arch packages…"
    sudo pacman -Sy --noconfirm \
        python-pip python-virtualenv \
        python-pyqt5 qt5-svg qt5-webengine \
        2>/dev/null || warn "Some pacman packages may have been skipped (non-fatal)"
    ok "System packages ready"

elif [[ "$PKG_MGR" == "brew" ]]; then
    if ! command -v brew &>/dev/null; then
        die "Homebrew not found. Install it from https://brew.sh first."
    fi
    info "Installing macOS Homebrew packages…"
    brew install python@3.11 pyqt@5 2>/dev/null || warn "Some brew packages may have been skipped (non-fatal)"
    ok "System packages ready"
else
    warn "Skipping system packages – install manually if needed"
fi

# ── Virtual environment ───────────────────────────────────────────────────────
section "Setting up virtual environment"
VENV_DIR="$(pwd)/.venv"

if [[ -d "$VENV_DIR" ]]; then
    warn "Existing .venv found – recreating"
    rm -rf "$VENV_DIR"
fi

"$PYTHON" -m venv "$VENV_DIR"
ok "Virtual environment created at $VENV_DIR"

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtual environment activated"

# Upgrade pip/wheel silently
pip install --upgrade pip wheel setuptools -q

# ── Python packages ───────────────────────────────────────────────────────────
section "Installing Python packages"

# PyQt5 + extras – prefer system Qt on Linux (already installed above)
if [[ "$DISTRO" == "macos" ]]; then
    info "Installing PyQt5 via pip (macOS)…"
    pip install PyQt5 PyQt5-Qt5 PyQt5-sip PyQtWebEngine -q
else
    info "Installing PyQt5 via pip (Linux)…"
    # Use --no-build-isolation so it can link against the system Qt if available
    pip install PyQt5 PyQtWebEngine -q 2>/dev/null || \
    pip install PyQt5 PyQtWebEngine -q --extra-index-url https://pypi.org/simple/ || \
    warn "PyQt5 pip install had issues – system packages may cover this"
fi

info "Installing core dependencies…"
pip install -q \
    "bcrypt>=4.0" \
    "certifi>=2024.1" \
    "chardet>=5.0" \
    "beautifulsoup4>=4.12" \
    "pycryptodome>=3.20"

ok "All Python packages installed"

# ── Verify imports ────────────────────────────────────────────────────────────
section "Verifying installation"
ERRORS=0

check_import() {
    local mod="$1"; local label="${2:-$1}"
    if "$PYTHON" -c "import $mod" 2>/dev/null; then
        ok "$label"
    else
        warn "Cannot import $label – check installation"
        ((ERRORS++)) || true
    fi
}

check_import "PyQt5.QtWidgets"          "PyQt5 (core)"
check_import "PyQt5.QtSvg"             "PyQt5.QtSvg"
check_import "PyQt5.QtWebEngineWidgets" "PyQt5.QtWebEngine"
check_import "bcrypt"                   "bcrypt"
check_import "certifi"                  "certifi"
check_import "chardet"                  "chardet"
check_import "bs4"                      "beautifulsoup4"
check_import "Crypto.Cipher"            "pycryptodome"

# ── Launcher script ───────────────────────────────────────────────────────────
section "Creating launcher"
cat > mailshield.sh << 'LAUNCH'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/.venv/bin/activate"

# Required for PyQt5 WebEngine on some systems
export QTWEBENGINE_DISABLE_SANDBOX=1
# Wayland compatibility
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

exec python "$DIR/main.py" "$@"
LAUNCH
chmod +x mailshield.sh
ok "Launcher: ./mailshield.sh"

# ── Desktop shortcut (Linux only) ─────────────────────────────────────────────
if [[ "$OS" == "Linux" ]]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/mailshield.desktop" << DESKTOP
[Desktop Entry]
Name=MailShield
Comment=Secure Email Client
Exec=$(pwd)/mailshield.sh
Icon=$(pwd)/assets/icon.png
Terminal=false
Type=Application
Categories=Network;Email;
DESKTOP
    ok "Desktop shortcut created (search 'MailShield' in your app launcher)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
if [[ "$ERRORS" -eq 0 ]]; then
    echo -e "${GREEN}  ✓  Installation complete!${NC}"
else
    echo -e "${YELLOW}  ⚠  Installation finished with $ERRORS warning(s)${NC}"
fi
echo -e "${BOLD}══════════════════════════════════════════${NC}"
echo ""
echo "  Run MailShield:"
echo -e "    ${CYAN}./mailshield.sh${NC}"
echo ""
echo "  Or manually:"
echo -e "    ${CYAN}source .venv/bin/activate && python main.py${NC}"
echo ""