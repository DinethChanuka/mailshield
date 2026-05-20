#!/usr/bin/env python3
"""
MailShield – Entry Point (fixed)
Fix 1: QApplication is created BEFORE any module-level code that
        calls QFontDatabase (theme.py), preventing the fatal abort:
        "QFontDatabase: Must construct a QGuiApplication first".
Fix 2: Removed unused QtMsgType import that could fail on some
        PyQt5 builds.
"""
import sys
import logging
from pathlib import Path

# ── Qt bootstrap ──────────────────────────────────────────────────────
# QApplication MUST exist before importing theme (or any module that
# calls QFontDatabase at module level).  We set the HiDPI attributes
# first because they must be set before the QApplication constructor.
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
# Required: QtWebEngineWidgets needs this set before QApplication is created,
# otherwise importing it later raises ImportError.
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

# Create the application instance early – main() will reuse it via
# QApplication.instance() so there is never a second QApplication.
_bootstrap_app = QApplication(sys.argv)
_bootstrap_app.setApplicationName("MailShield")
_bootstrap_app.setOrganizationName("MailShield")

# ── Qt message handler (suppress internal QPainter noise) ────────────
from PyQt5.QtCore import qInstallMessageHandler

_qt_log = logging.getLogger("qt")


def _qt_message_handler(mode, context, message):
    msg = message.strip()
    _NOISE = (
        "QPainter::begin",
        "QPainter::setWorldTransform",
        "QPainter::translate",
        "QWidgetEffectSourcePrivate",
        "QPainter::worldTransform",
    )
    if any(n in msg for n in _NOISE):
        _qt_log.debug(msg)
        return
    _qt_log.warning(msg)


qInstallMessageHandler(_qt_message_handler)

# ── Application imports (safe now that QApplication exists) ──────────
from theme import apply_theme, SETTINGS
from engine import APP_DIR
from main_window import MainWindow
from dialogs import LoginDialog

# ── Logging ───────────────────────────────────────────────────────────
LOG_PATH = APP_DIR / "mailshield.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("mailshield")


def main():
    # Reuse the QApplication created at module level (never create a
    # second one – that causes undefined behaviour in Qt).
    app = QApplication.instance()
    if app is None:
        # Fallback: should not happen, but guard defensively.
        app = QApplication(sys.argv)
        app.setApplicationName("MailShield")
        app.setOrganizationName("MailShield")

    apply_theme(app)

    try:
        from PyQt5.QtWidgets import QDialog, QMessageBox

        login = LoginDialog()
        if login.exec_() == QDialog.Accepted:
            window = MainWindow(login.user)
            window.show()
            sys.exit(app.exec_())
        else:
            sys.exit(0)

    except Exception as exc:
        import traceback
        from PyQt5.QtWidgets import QMessageBox

        log.critical(f"Fatal: {exc}\n{traceback.format_exc()}")
        QMessageBox.critical(
            None,
            "MailShield – Startup Error",
            f"Failed to start:\n\n{exc}\n\nSee log:\n{LOG_PATH}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
