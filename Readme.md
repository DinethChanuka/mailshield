# MailShield

**Secure, privacy-first desktop email client** with built-in AI-powered threat detection. MailShield connects to any standard IMAP/SMTP server and silently scores every message for phishing, spoofing, and social-engineering attacks before you ever open it.

---

## Features

- **Multi-account inbox** — Gmail, Outlook, Yahoo, ProtonMail (Bridge), or any custom IMAP server
- **Real-time security scoring** — every email is analysed across 10+ detection layers the moment it arrives
- **Threat detection layers**
  - URL structure inspection and effective-domain extraction
  - Punycode / homograph domain attacks
  - Percent-encoding normalisation (`%70%61%79%70%61%6c` → `paypal`)
  - Tunnel and free-host detection (ngrok, trycloudflare, serveo, …)
  - Invisible-text and zero-width character detection
  - Link/display-text mismatch (`<a href=evil>paypal.com</a>`)
  - SPF/DKIM header forensics and Return-Path mismatch
  - Sender reputation and lookalike domain scoring
- **AES-256-GCM encrypted credential storage** — passwords never stored in plain text
- **Compose & send** — full SMTP support with attachment handling
- **Dark / light theme** with customisable accent colour
- **Toast, banner, and modal alert system** for sync events and auth failures
- **Attachment viewer** and inline image rendering via Qt WebEngine
- **Background sync** — IMAP syncing runs off the GUI thread; the UI stays responsive

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.9 – 3.12 |
| PyQt5 | ≥ 5.15 |
| PyQtWebEngine | ≥ 5.15 |
| bcrypt | ≥ 4.0 |
| beautifulsoup4 | ≥ 4.12 |
| certifi | ≥ 2024.1 |
| chardet | ≥ 5.0 |
| pycryptodome | ≥ 3.20 |

### Operating systems

| Platform | Status |
|---|---|
| Ubuntu 20.04 + / Debian 11 + | ✅ Supported |
| Fedora 36 + | ✅ Supported |
| Arch Linux | ✅ Supported |
| macOS 12 + (Homebrew) | ✅ Supported |
| Windows 10 / 11 (64-bit) | ✅ Supported |

---

## Installation

### Linux / macOS

```bash
# 1. Clone or download the project
git clone https://github.com/yourname/mailshield.git
cd mailshield

# 2. Make the installer executable and run it
chmod +x install.sh
./install.sh
```

The script will:
- Detect your distro and install system Qt libraries via `apt`, `dnf`, `pacman`, or `brew`
- Create an isolated Python virtual environment at `.venv/`
- Install all Python dependencies
- Write a `mailshield.sh` launcher
- Register a desktop shortcut (Linux only)

### Windows

```
1. Download or clone the project folder
2. Double-click  install.bat
3. Follow the on-screen prompts
```

The script will:
- Locate Python 3.9–3.12 (via the `py` launcher or `PATH`)
- Create an isolated virtual environment at `.venv\`
- Install all Python dependencies
- Write a `mailshield.bat` launcher
- Create a desktop shortcut

> **Python not found?**  
> Download from [python.org/downloads](https://www.python.org/downloads/) and check **"Add Python to PATH"** during setup.

---

## First Launch

### Linux / macOS
```bash
./mailshield.sh
```

### Windows
Double-click **mailshield.bat** or the **MailShield** desktop shortcut.

### Manual (any platform)
```bash
# activate the venv first
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

python main.py
```

On first launch MailShield will ask you to create a local account (username + password). This account is stored locally and is separate from your email credentials.

---

## Adding an Email Account

1. Open **Settings → Accounts → Add Account**
2. Choose your provider: **Gmail · Outlook · Yahoo · ProtonMail · Custom IMAP**
3. Enter your email address and an **App Password** (see below)
4. Click **Test Connection** — MailShield will verify the IMAP login before saving

### App Passwords

Most providers require an App Password (a separate password for third-party clients):

| Provider | Where to create |
|---|---|
| **Gmail** | [myaccount.google.com → Security → App Passwords](https://myaccount.google.com/apppasswords) — requires 2-Step Verification enabled |
| **Outlook / Hotmail** | [account.microsoft.com → Security → App Passwords](https://account.live.com/proofs/manage) — only available when 2FA is enabled |
| **Yahoo Mail** | [account.security.yahoo.com → Generate App Password](https://login.yahoo.com/account/security) |
| **ProtonMail** | Install [Proton Mail Bridge](https://proton.me/mail/bridge) and use the Bridge password |
| **Custom IMAP** | Use your normal password unless your provider specifies otherwise |

---

## Data & Privacy

- All data is stored **locally** in `~/.mailshield/` (Linux/macOS) or `%USERPROFILE%\.mailshield\` (Windows)
- Email credentials are encrypted with **AES-256-GCM** using a key stored in `~/.mailshield/.key`
- No data is sent to any external server; all security analysis runs **on-device**
- The database is a standard SQLite file: `~/.mailshield/mailshield.db`

---

## Project Structure

```
mailshield/
├── main.py                  Entry point – bootstraps QApplication, shows login
├── main_window.py           Main window, email list, detail view, compose
├── engine.py                IMAP sync, SMTP send, SQLite storage, encryption
├── security_engine.py       Threat-detection engine (10+ analysis layers)
├── workers.py               Background QThread workers for IMAP/SMTP
├── dialogs.py               Login, register, account settings, compose dialogs
├── alerts.py                Toast, banner, and modal error alert system
├── components.py            Shared UI widgets (cards, avatars, email list items)
├── theme.py                 Design tokens, dark/light palettes, QSS generation
├── motion.py                Animation helpers (fade, slide)
├── security_analysis_qss.py Scoped QSS for the security dashboard panel
├── utils.py                 Time formatting, shadow effects, IMAP/SMTP error mapping
├── install.sh               Linux / macOS installer
└── install.bat              Windows installer
```

---

## Manual Dependency Install

If you prefer to manage the environment yourself:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install \
    PyQt5 \
    PyQtWebEngine \
    "bcrypt>=4.0" \
    "certifi>=2024.1" \
    "chardet>=5.0" \
    "beautifulsoup4>=4.12" \
    "pycryptodome>=3.20"

python main.py
```

---

## Troubleshooting

### PyQt5 / WebEngine import errors (Linux)
```bash
# Ubuntu / Debian
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pyqt5.qtsvg

# Fedora
sudo dnf install python3-qt5 qt5-qtwebengine
```

### Black window / display issues (Linux Wayland)
```bash
export QT_QPA_PLATFORM=xcb
./mailshield.sh
```

### `QTWEBENGINE_DISABLE_SANDBOX` warning
This is expected on some systems where the Chromium sandbox is not supported. The launchers set this variable automatically; it does not affect security analysis.

### Authentication failed
- Make sure you are using an **App Password**, not your regular account password
- Gmail: ensure 2-Step Verification is active before App Passwords appear
- Outlook: App Passwords only appear when 2FA is enabled on the Microsoft account

### macOS: "cannot be opened because the developer cannot be verified"
```bash
xattr -dr com.apple.quarantine mailshield.sh
```

---

## License

MIT License — see `LICENSE` for details.