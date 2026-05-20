"""
MailShield – Modal Dialogs v3.2
Fixes:
 • account_svc.delete_account() (correct method name, was remove_account)
 • Remove button text visible on all themes (explicit color override)
 • Apply buttons in Settings sections
 • Light-theme button labels (explicit white/black text per theme)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, QByteArray, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QPushButton,
    QToolButton,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QTabWidget,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFormLayout,
    QSlider,
    QCheckBox,
    QColorDialog,
    QApplication,
    QScrollArea,
    QSizePolicy,
)

from theme import C, ThemeManager, ACCENT_PRESETS, SETTINGS, apply_theme
from utils import make_avatar, map_imap_error, map_smtp_error
from components import CardWidget, PasswordField
from alerts import fade_in_widget

# ── Inline SVG icon library for dialogs ────────────────────────────────
_DIALOG_SVGS: dict = {
    "appearance": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <path d="M12 2a10 10 0 0 1 0 20"/>
      <path d="M2 12h20M12 2c-2.76 4-2.76 16 0 20M12 2c2.76 4 2.76 16 0 20"/>
    </svg>""",
    "accounts": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>""",
    "sync": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="23 4 23 10 17 10"/>
      <polyline points="1 20 1 14 7 14"/>
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>""",
    "security": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      <polyline points="9 12 11 14 15 10"/>
    </svg>""",
    "advanced": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>
    </svg>""",
    "mail": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
      <polyline points="22,6 12,13 2,6"/>
    </svg>""",
    "phone": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5
               19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11
               2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45
               2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339
               1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
    </svg>""",
    "building": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="3" width="20" height="18" rx="2"/>
      <line x1="8" y1="10" x2="8" y2="10.01"/>
      <line x1="12" y1="10" x2="12" y2="10.01"/>
      <line x1="16" y1="10" x2="16" y2="10.01"/>
      <line x1="8" y1="14" x2="8" y2="14.01"/>
      <line x1="12" y1="14" x2="12" y2="14.01"/>
      <line x1="16" y1="14" x2="16" y2="14.01"/>
    </svg>""",
    "person": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>""",
    "add_contact": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <line x1="19" y1="8" x2="19" y2="14"/>
      <line x1="22" y1="11" x2="16" y2="11"/>
    </svg>""",
    "edit": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>""",
    "trash": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
      <path d="M10 11v6M14 11v6"/>
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
    </svg>""",
    "search": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>""",
    "close": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>""",
}


def _svg_pixmap(name: str, size: int, color: str) -> QPixmap:
    """Render a named inline SVG at the given size and color."""
    raw = _DIALOG_SVGS.get(name, "")
    if not raw:
        return QPixmap()
    svg_bytes = QByteArray(raw.replace("{c}", color).encode())
    renderer = QSvgRenderer(svg_bytes)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return pm


def _svg_icon(name: str, size: int = 16, color: str = "") -> QIcon:
    col = color or C("text_secondary")
    pm = _svg_pixmap(name, size, col)
    return QIcon(pm) if not pm.isNull() else QIcon()


def _svg_label(name: str, size: int = 16, color: str = "") -> "QLabel":
    """Return a fixed-size QLabel showing an SVG icon."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    col = color or C("text_muted")
    pm = _svg_pixmap(name, size, col)
    if not pm.isNull():
        lbl.setPixmap(pm)
    lbl.setStyleSheet("background:transparent;border:none;")
    return lbl


try:
    from engine import (
        Account,
        EmailMsg,
        Contact,
        user_svc,
        account_svc,
        email_svc,
        ContactService,
        send_email,
        db,
        APP_DIR,
        PROVIDER_CONFIG,
    )
except ImportError:
    pass

log = logging.getLogger("mailshield")


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C('border')};")
    return f


def _fw(label, widget):
    w = QWidget()
    ly = QVBoxLayout(w)
    ly.setSpacing(4)
    ly.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(f"font-size:11px;color:{C('text_muted')};font-weight:600;")
    ly.addWidget(lbl)
    ly.addWidget(widget)
    return w


def _danger_btn(text: str) -> QPushButton:
    """A Remove/Delete button whose text is always readable regardless of theme."""
    btn = QPushButton(text)
    btn.setFixedHeight(30)
    btn.setStyleSheet(
        f"QPushButton{{background:transparent;color:{C('danger')};"
        f"border:1px solid {C('danger')};border-radius:6px;"
        f"font-size:12px;font-weight:600;padding:0 12px;min-height:0;}}"
        f"QPushButton:hover{{background:{C('danger')};color:#ffffff;}}"
        f"QPushButton:disabled{{color:{C('text_muted')};border-color:{C('border')};}}"
    )
    return btn


def input_style():
    return f"""
QLineEdit {{
    background: {C('surface_elevated')};
    border: 1px solid {C('border')};
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 14px;
    color: {C('text_primary')};
}}

QLineEdit:focus {{
    border: 1.5px solid {C('accent')};
    background: {C('surface')};
}}
"""


# ── Login ──────────────────────────────────────────────────────────────
class LoginDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MailShield – Sign In")
        self.setModal(True)
        self.resize(440, 530)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.user = None
        self._build()
        fade_in_widget(self, 220)

    def _build(self):
        # Explicitly set background so the dialog respects the saved theme
        self.setStyleSheet(f"""
QDialog {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {C('bg')},
        stop:1 {C('surface')});
}}

QTabWidget::pane {{
    border: none;
    background: transparent;
    margin-top: 8px;
}}

QTabBar {{
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background: transparent;
    padding: 15px 18px;
    margin-right: 6px;
    font-size: 10px;
    font-weight: 500;
    color: {C('text_muted')};
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:selected {{
    color: {C('accent')};
    border-bottom: 2px solid {C('accent')};
}}

QTabBar::tab:hover {{
    color: {C('text_primary')};
}}
""")
        ly = QVBoxLayout(self)
        ly.setContentsMargins(40, 30, 40, 30)
        ly.setSpacing(16)

        # Icon badge
        shield = QLabel("M")
        shield.setFixedSize(64, 64)
        shield.setAlignment(Qt.AlignCenter)
        shield.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {C('accent')},stop:1 {C('gradient_end')});"
            f"color:#fff;border-radius:18px;font-size:26px;font-weight:800;"
            f"border:2px solid {C('accent')}44;"
        )
        ly.addWidget(shield, 0, Qt.AlignHCenter)

        title = QLabel("MailShield")
        title.setStyleSheet(
            f"font-size:26px;font-weight:800;color:{C('text_primary')};letter-spacing:-0.5px;"
        )
        ly.addWidget(title, 0, Qt.AlignHCenter)

        sub = QLabel("Secure Email Intelligence")
        sub.setStyleSheet(
            f"font-size:13px;color:{C('text_muted')};letter-spacing:0.3px;"
        )
        ly.addWidget(sub, 0, Qt.AlignHCenter)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color:{C('border')};")
        ly.addWidget(div)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Sign In tab
        si = QWidget()
        si.setStyleSheet(f"background:{C('surface')};border-radius:10px;")
        sil = QVBoxLayout(si)
        sil.setSpacing(14)
        sil.setContentsMargins(0, 18, 0, 4)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username or Email")
        self.username_edit.setMinimumHeight(46)
        self.username_edit.setStyleSheet(input_style())
        sil.addWidget(self.username_edit)
        self.pwd_field = PasswordField("Password")
        self.pwd_field.setStyleSheet(input_style())
        sil.addWidget(self.pwd_field)
        self.error_lbl = self._err_lbl()
        sil.addWidget(self.error_lbl)
        sign_btn = QPushButton("Sign In")
        sign_btn.setMinimumHeight(48)
        sign_btn.setStyleSheet(f"""
QPushButton {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {C('accent')},
        stop:1 {C('gradient_end')});
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 700;
    padding: 12px;
}}

QPushButton:hover {{
    opacity: 0.9;
}}

QPushButton:pressed {{
    padding-top: 14px;
    padding-bottom: 10px;
}}
""")
        sign_btn.clicked.connect(self._login)
        self.pwd_field.returnPressed.connect(self._login)
        sil.addWidget(sign_btn)
        sil.addStretch()
        tabs.addTab(si, "Sign In")

        # Register tab
        reg = QWidget()
        reg.setStyleSheet(f"background:{C('surface')};border-radius:10px;")
        regl = QVBoxLayout(reg)
        regl.setSpacing(10)
        regl.setContentsMargins(0, 18, 0, 4)

        def _inp(ph):
            w = QLineEdit()
            w.setPlaceholderText(ph)
            w.setMinimumHeight(44)
            w.setStyleSheet(
                f"QLineEdit{{background:{C('surface_elevated')};border:1.5px solid {C('border')};"
                f"border-radius:10px;padding:10px 16px;font-size:13px;color:{C('text_primary')};}}"
                f"QLineEdit:focus{{border-color:{C('accent')};}}"
            )
            return w

        self.reg_user = _inp("Username")
        self.reg_email = _inp("Email (optional)")
        self.reg_pwd = PasswordField("Password (min. 6 chars)")
        self.reg_conf = PasswordField("Confirm Password")
        self.reg_err = self._err_lbl()
        reg_btn = QPushButton("Create Account")
        reg_btn.setMinimumHeight(48)
        reg_btn.setStyleSheet(
            f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C('accent')},stop:1 {C('gradient_end')});"
            f"color:#fff;border:none;border-radius:10px;"
            f"font-size:14px;font-weight:700;}}"
        )
        reg_btn.clicked.connect(self._register)
        for w in (
            self.reg_user,
            self.reg_email,
            self.reg_pwd,
            self.reg_conf,
            self.reg_err,
            reg_btn,
        ):
            regl.addWidget(w)
        regl.addStretch()
        tabs.addTab(reg, "Create Account")
        # ===== GLASS CARD WRAPPER =====
        card = QFrame()
        card.setObjectName("mainCard")

        card.setStyleSheet(f"""
#mainCard {{
    background: {C('surface')};
    border: 1px solid {C('border')};
    border-radius: 16px;
}}
""")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # Move tabs INTO card
        card_layout.addWidget(tabs)

        # Add card to main layout
        ly.addWidget(card)

    def _err_lbl(self):
        l = QLabel("")
        l.setWordWrap(True)
        l.setVisible(False)
        l.setStyleSheet(
            f"color:{C('danger')};background:{C('danger')}18;"
            f"border:1px solid {C('danger')}33;border-radius:8px;padding:10px;font-size:12px;"
        )
        return l

    def _show_err(self, msg, reg=False):
        lbl = self.reg_err if reg else self.error_lbl
        lbl.setText(msg)
        lbl.setVisible(True)
        fade_in_widget(lbl, 130)

    def _login(self):
        self.error_lbl.setVisible(False)
        u = self.username_edit.text().strip()
        p = self.pwd_field.text()
        if not u or not p:
            self._show_err("Please enter username and password.")
            return
        try:
            user = user_svc.login(u, p)
            if user:
                self.user = user
                self.accept()
            else:
                self._show_err("Invalid username or password.")
        except Exception as e:
            log.error(f"Login: {e}")
            self._show_err(str(e))

    def _register(self):
        self.reg_err.setVisible(False)
        u = self.reg_user.text().strip()
        em = self.reg_email.text().strip()
        p = self.reg_pwd.text()
        pc = self.reg_conf.text()
        if not u or not p:
            self._show_err("Username and password required.", reg=True)
            return
        if len(p) < 6:
            self._show_err("Password min. 6 characters.", reg=True)
            return
        if p != pc:
            self._show_err("Passwords do not match.", reg=True)
            return
        try:
            user = user_svc.register(u, p, em)
            if user:
                self.user = user
                self.accept()
            else:
                self._show_err("Username already taken.", reg=True)
        except Exception as e:
            log.error(f"Register: {e}")
            self._show_err(str(e), reg=True)


# ── Add Account ────────────────────────────────────────────────────────
class AddAccountDialog(QDialog):
    def __init__(self, parent, user_id):
        super().__init__(parent)
        self.user_id = user_id
        self.setWindowTitle("Add Email Account")
        self.setModal(True)
        self.resize(500, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        fade_in_widget(self, 180)

    def _build(self):
        # ── Full dialog background – must match theme so no black panels ──
        self.setStyleSheet(
            f"QDialog{{background:{C('bg')};}}"
            f"QLabel{{background:transparent;color:{C('text_primary')};}}"
            f"QLineEdit{{background:{C('surface_elevated')};border:1px solid {C('border')};"
            f"border-radius:8px;padding:8px 12px;color:{C('text_primary')};font-size:13px;}}"
            f"QLineEdit:focus{{border-color:{C('accent')};}}"
            f"QComboBox{{background:{C('surface_elevated')};border:1px solid {C('border')};"
            f"border-radius:8px;padding:6px 12px;color:{C('text_primary')};font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:{C('surface')};color:{C('text_primary')};"
            f"border:1px solid {C('border')};}}"
        )
        ly = QVBoxLayout(self)
        ly.setSpacing(16)
        ly.setContentsMargins(28, 28, 28, 24)
        ly.addWidget(
            QLabel(
                "Add Email Account",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )
        hint = QLabel(
            "Gmail, Yahoo, Outlook: use an App Password — not your regular password."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"font-size:12px;color:{C('text_muted')};background:{C('accent')}18;"
            f"border:1px solid {C('accent')}33;border-radius:8px;padding:10px;"
        )
        ly.addWidget(hint)

        card = CardWidget()
        cl = QVBoxLayout(card)
        cl.setSpacing(14)
        cl.setContentsMargins(18, 18, 18, 18)
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumHeight(38)
        for p in ["gmail", "outlook", "yahoo", "custom"]:
            self.provider_combo.addItem(p.title(), p)
        self.provider_combo.currentIndexChanged.connect(self._on_provider)
        cl.addWidget(_fw("Provider", self.provider_combo))

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("your@email.com")
        self.email_edit.setMinimumHeight(38)
        cl.addWidget(_fw("Email Address", self.email_edit))

        self.pwd_field = PasswordField("App password / IMAP password")
        cl.addWidget(_fw("Password", self.pwd_field))

        self.custom_frame = QWidget()
        cf = QVBoxLayout(self.custom_frame)
        cf.setSpacing(10)
        cf.setContentsMargins(0, 8, 0, 0)
        self.imap_edit = QLineEdit()
        self.imap_edit.setPlaceholderText("imap.example.com")
        self.imap_edit.setMinimumHeight(38)
        cf.addWidget(_fw("IMAP Host", self.imap_edit))
        self.smtp_edit = QLineEdit()
        self.smtp_edit.setPlaceholderText("smtp.example.com")
        self.smtp_edit.setMinimumHeight(38)
        cf.addWidget(_fw("SMTP Host", self.smtp_edit))
        ports = QHBoxLayout()
        ports.setSpacing(12)
        self.imap_port = QLineEdit("993")
        self.imap_port.setMinimumHeight(38)
        self.smtp_port = QLineEdit("587")
        self.smtp_port.setMinimumHeight(38)
        ports.addWidget(_fw("IMAP Port", self.imap_port))
        ports.addWidget(_fw("SMTP Port", self.smtp_port))
        cf.addLayout(ports)
        self.custom_frame.setVisible(False)
        cl.addWidget(self.custom_frame)
        ly.addWidget(card)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        self.status_lbl.setStyleSheet("font-size:12px;")
        ly.addWidget(self.status_lbl)
        ly.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(10)
        test_btn = QPushButton("Test Connection")
        test_btn.setProperty("class", "secondary")
        test_btn.setFixedHeight(38)
        test_btn.clicked.connect(self._test)
        btns.addWidget(test_btn)
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setProperty("class", "secondary")
        cancel.setFixedHeight(38)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        add_btn = QPushButton("Add Account")
        add_btn.setFixedHeight(38)
        add_btn.clicked.connect(self._add)
        btns.addWidget(add_btn)
        ly.addLayout(btns)

    def _on_provider(self, _):
        self.custom_frame.setVisible(self.provider_combo.currentData() == "custom")

    def _status(self, msg, ok=True):
        self.status_lbl.setText(msg)
        self.status_lbl.setStyleSheet(
            f"font-size:12px;color:{C('success') if ok else C('danger')};"
        )
        self.status_lbl.setVisible(True)

    def _test(self):
        em = self.email_edit.text().strip()
        pw = self.pwd_field.text()
        if not em or not pw:
            self._status("Fill email and password first.", ok=False)
            return
        self._status("Testing connection…")
        QApplication.processEvents()
        try:
            ok, msg = account_svc.test_connection(
                self.provider_combo.currentData(),
                em,
                pw,
                imap_host=self.imap_edit.text().strip(),
            )
            if ok:
                self._status(f"Connected: {msg}")
            else:
                t, d = map_imap_error(msg)
                self._status(f"{t} — {d}", ok=False)
        except Exception as e:
            t, d = map_imap_error(str(e))
            self._status(f"{t} — {d}", ok=False)

    def _add(self):
        prov = self.provider_combo.currentData()
        em = self.email_edit.text().strip().lower()
        pw = self.pwd_field.text()
        if not em or not pw:
            self._status("Email and password are required.", ok=False)
            return
        try:
            acc = account_svc.add_account(
                self.user_id,
                prov,
                em,
                pw,
                imap_host=self.imap_edit.text().strip() if prov == "custom" else "",
                smtp_host=self.smtp_edit.text().strip() if prov == "custom" else "",
            )
            if acc:
                self.accept()
            else:
                # ── Reactivate a previously removed account ────────────
                # delete_account() only soft-deletes (is_active=0), leaving the
                # UNIQUE(user_id, email) row intact.  If we find it, reactivate it.
                existing = db.one(
                    "SELECT id FROM accounts WHERE user_id=? AND email=?",
                    (self.user_id, em),
                )
                if existing:
                    cfg = PROVIDER_CONFIG.get(prov, ("", 993, "", 587, True))
                    imap_h = (
                        self.imap_edit.text().strip() if prov == "custom" else cfg[0]
                    )
                    smtp_h = (
                        self.smtp_edit.text().strip() if prov == "custom" else cfg[2]
                    )
                    from engine import encrypt as _enc

                    db.run(
                        """UPDATE accounts
                           SET is_active=1, provider=?, enc_password=?,
                               imap_host=?, smtp_host=?, last_sync=NULL
                           WHERE id=?""",
                        (prov, _enc(pw), imap_h, smtp_h, existing["id"]),
                    )
                    self.accept()
                else:
                    self._status("Account with this email already exists.", ok=False)
        except Exception as e:
            log.error(f"AddAccount: {e}")
            t, d = map_imap_error(str(e))
            self._status(f"{t} — {d}", ok=False)


# ── Compose ────────────────────────────────────────────────────────────
class ComposeDialog(QDialog):
    def __init__(
        self, parent, accounts, default_account=None, reply_to=None, forward=None
    ):
        super().__init__(parent)
        self.accounts = accounts
        self.default_account = default_account or (accounts[0] if accounts else None)
        self.reply_to = reply_to
        self.forward = forward
        self.attach_paths: List[str] = []
        self.setWindowTitle("Compose")
        self.setModal(True)
        self.resize(740, 590)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        fade_in_widget(self, 180)

    def _build(self):
        self.setStyleSheet(f"background:{C('bg')};")
        ly = QVBoxLayout(self)
        ly.setSpacing(0)
        ly.setContentsMargins(0, 0, 0, 0)

        hdr = QFrame()
        hdr.setFixedHeight(52)
        hdr.setStyleSheet(
            f"background:{C('surface')};border-bottom:1px solid {C('border')};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        kind = (
            "Reply" if self.reply_to else "Forward" if self.forward else "New Message"
        )
        hl.addWidget(
            QLabel(
                kind,
                styleSheet=f"font-size:15px;font-weight:700;color:{C('text_primary')};",
            )
        )
        hl.addStretch()
        xb = QPushButton("×")
        xb.setFixedSize(28, 28)
        xb.setStyleSheet(
            f"QPushButton{{background:{C('surface_elevated')};color:{C('text_muted')};"
            f"border:none;border-radius:14px;font-size:17px;padding:0;min-height:0;}}"
            f"QPushButton:hover{{background:{C('danger')};color:#fff;}}"
        )
        xb.clicked.connect(self.reject)
        hl.addWidget(xb)
        ly.addWidget(hdr)

        form = QWidget()
        form.setStyleSheet(f"background:{C('bg')};")
        fl = QVBoxLayout(form)
        fl.setContentsMargins(20, 14, 20, 14)
        fl.setSpacing(8)

        def fr(lbl_text, widget):
            r = QHBoxLayout()
            l = QLabel(lbl_text)
            l.setFixedWidth(52)
            l.setStyleSheet(f"color:{C('text_muted')};font-size:12px;font-weight:600;")
            r.addWidget(l)
            r.addWidget(widget)
            return r

        self.from_combo = QComboBox()
        self.from_combo.setMinimumHeight(36)
        for a in self.accounts:
            self.from_combo.addItem(f"{a.display_name or a.email}  <{a.email}>", a.id)
        if self.default_account:
            idx = next(
                (
                    i
                    for i, a in enumerate(self.accounts)
                    if a.id == self.default_account.id
                ),
                0,
            )
            self.from_combo.setCurrentIndex(idx)
        fl.addLayout(fr("From:", self.from_combo))
        fl.addWidget(_sep())

        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("recipient@example.com, …")
        self.to_edit.setMinimumHeight(36)
        fl.addLayout(fr("To:", self.to_edit))
        fl.addWidget(_sep())

        self.cc_edit = QLineEdit()
        self.cc_edit.setPlaceholderText("CC (optional)")
        self.cc_edit.setMinimumHeight(36)
        fl.addLayout(fr("CC:", self.cc_edit))
        fl.addWidget(_sep())

        self.subj_edit = QLineEdit()
        self.subj_edit.setMinimumHeight(36)
        fl.addLayout(fr("Subject:", self.subj_edit))
        fl.addWidget(_sep())

        self.body_edit = QTextEdit()
        self.body_edit.setMinimumHeight(220)
        self.body_edit.setStyleSheet(
            f"QTextEdit{{border:none;background:{C('bg')};color:{C('text')};font-size:14px;padding:4px;}}"
        )
        fl.addWidget(self.body_edit, 1)

        if self.reply_to:
            self.to_edit.setText(self.reply_to.from_email or "")
            self.subj_edit.setText(f"Re: {self.reply_to.subject or ''}")
            self.body_edit.setPlainText(
                f"\n\n--- Original ---\nFrom: {self.reply_to.from_email}\n{self.reply_to.body_text or ''}"
            )
        elif self.forward:
            self.subj_edit.setText(f"Fwd: {self.forward.subject or ''}")
            self.body_edit.setPlainText(
                f"\n\n--- Forwarded ---\nFrom: {self.forward.from_email}\n{self.forward.body_text or ''}"
            )
        ly.addWidget(form, 1)

        footer = QFrame()
        footer.setFixedHeight(56)
        footer.setStyleSheet(
            f"background:{C('surface')};border-top:1px solid {C('border')};"
        )
        ftl = QHBoxLayout(footer)
        ftl.setContentsMargins(20, 0, 20, 0)
        ftl.setSpacing(10)
        self.attach_btn = QPushButton("Attach")
        self.attach_btn.setProperty("class", "secondary")
        self.attach_btn.clicked.connect(self._attach)
        ftl.addWidget(self.attach_btn)
        ftl.addStretch()
        discard = QPushButton("Discard")
        discard.setProperty("class", "secondary")
        discard.clicked.connect(self.reject)
        ftl.addWidget(discard)
        send_btn = QPushButton("Send")
        send_btn.setMinimumWidth(100)
        send_btn.clicked.connect(self._send)
        ftl.addWidget(send_btn)
        ly.addWidget(footer)

    def _attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach Files")
        if files:
            self.attach_paths.extend(files)
            self.attach_btn.setText(f"Attached ({len(self.attach_paths)})")

    def _send(self):
        to = self.to_edit.text().strip()
        subj = self.subj_edit.text().strip() or "(No Subject)"
        body = self.body_edit.toPlainText().strip()
        if not to:
            QMessageBox.warning(
                self, "Missing Recipient", "Enter at least one recipient."
            )
            return
        acc_id = self.from_combo.currentData()
        acc = next((a for a in self.accounts if a.id == acc_id), None)
        if not acc:
            QMessageBox.warning(self, "No Account", "Select a sending account.")
            return
        try:
            send_email(
                acc,
                to,
                subj,
                body,
                cc=self.cc_edit.text().strip(),
                attachment_paths=self.attach_paths or None,
            )
            self.accept()
        except Exception as e:
            log.error(f"Send: {e}")
            t, d = map_smtp_error(str(e))
            QMessageBox.critical(self, t, d)


# ── Settings ───────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    theme_changed = pyqtSignal()
    account_changed = pyqtSignal()

    def __init__(self, parent, user_id, accounts):
        super().__init__(parent)
        self.user_id = user_id
        self.accounts = accounts
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(700, 580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        fade_in_widget(self, 180)

    def _build(self):
        self.setStyleSheet(f"background:{C('bg')};")
        main = QHBoxLayout(self)
        main.setSpacing(0)
        main.setContentsMargins(0, 0, 0, 0)

        # Sidebar nav – store reference so _refresh_dialog_styles can find it reliably
        nav = QFrame()
        nav.setObjectName("SettingsNavSidebar")
        nav.setFixedWidth(180)
        nav.setStyleSheet(
            f"QFrame#SettingsNavSidebar{{background:{C('surface')};border-right:1px solid {C('border')};}}"
        )
        self._nav_frame = nav
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(12, 20, 12, 20)
        nl.setSpacing(4)
        nl.addWidget(
            QLabel(
                "Settings",
                styleSheet=f"font-size:16px;font-weight:700;color:{C('text_primary')};padding:0 8px 12px;",
            )
        )

        self._stack = QTabWidget()
        self._stack.tabBar().setVisible(False)
        self._stack.setStyleSheet("QTabWidget::pane{border:none;}")
        self._nav_btns = {}

        _SVG_KEYS = {
            "Appearance": "appearance",
            "Accounts": "accounts",
            "Sync": "sync",
            "Security": "security",
            "Advanced": "advanced",
        }
        for idx, (label, builder) in enumerate(
            [
                ("Appearance", self._page_appearance),
                ("Accounts", self._page_accounts),
                ("Sync", self._page_sync),
                ("Security", self._page_security),
                ("Advanced", self._page_advanced),
            ]
        ):
            btn = self._mkbtn(label, _SVG_KEYS.get(label, "advanced"))
            btn.clicked.connect(lambda _, i=idx: self._switch(i))
            nl.addWidget(btn)
            self._nav_btns[label] = btn

            page = QScrollArea()
            page.setWidgetResizable(True)
            page.setFrameShape(QFrame.NoFrame)
            page.setStyleSheet("QScrollArea{background:transparent;border:none;}")
            inner = QWidget()
            inner.setStyleSheet(f"background:{C('bg')};")
            pl = QVBoxLayout(inner)
            pl.setContentsMargins(28, 24, 28, 24)
            pl.setSpacing(16)
            builder(pl)
            pl.addStretch()
            page.setWidget(inner)
            self._stack.addTab(page, label)

        nl.addStretch()
        nl.addWidget(
            QLabel(
                "MailShield v3.2",
                styleSheet=f"color:{C('text_muted')};font-size:11px;padding:0 8px;",
            )
        )
        main.addWidget(nav)
        main.addWidget(self._stack, 1)
        self._switch(0)

    def _mkbtn(self, label: str, svg_key: str = "advanced") -> QToolButton:
        btn = QToolButton()
        btn.setText(f"  {label}")
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setFixedHeight(42)
        btn.setIconSize(QSize(17, 17))
        btn.setCheckable(True)
        btn._svg_key = svg_key  # stash for refresh
        self._refresh_nav_btn_style(btn, checked=False)
        return btn

    def _refresh_nav_btn_style(self, btn, checked: bool):
        svg_key = getattr(btn, "_svg_key", "advanced")
        color = C("accent") if checked else C("text_secondary")
        ico = _svg_icon(svg_key, 17, color)
        btn.setIcon(ico)
        active_bg = C("accent") + "22"
        btn.setStyleSheet(
            f"QToolButton{{text-align:left;padding-left:10px;border-radius:10px;"
            f"font-size:13px;color:{C('text_secondary')};background:transparent;"
            f"border:none;}}"
            f"QToolButton:hover{{background:{C('card_hover')};color:{C('text_primary')};}}"
            f"QToolButton:checked{{background:{active_bg};color:{C('accent')};font-weight:700;}}"
        )

    def _switch(self, idx):
        for i, (lbl, btn) in enumerate(self._nav_btns.items()):
            checked = i == idx
            btn.setChecked(checked)
            self._refresh_nav_btn_style(btn, checked)
        self._stack.setCurrentIndex(idx)

    def _refresh_dialog_styles(self):
        """Called after theme/accent change – nav sidebar + all page content rebuilt."""
        bg = C("bg")
        surf = C("surface")
        bdr = C("border")

        self.setStyleSheet(f"background:{bg};")

        # ── QTabWidget pane ────────────────────────────────────────────
        self._stack.setStyleSheet(
            f"QTabWidget::pane{{border:none;background:{bg};}}"
            f"QTabWidget{{background:{bg};}}"
        )

        # ── Nav sidebar – use stored ref, NOT findChild (which finds wrong QFrame) ──
        if hasattr(self, "_nav_frame") and self._nav_frame:
            self._nav_frame.setStyleSheet(
                f"QFrame#SettingsNavSidebar{{background:{surf};border-right:1px solid {bdr};}}"
            )
        for i, (lbl, btn) in enumerate(self._nav_btns.items()):
            self._refresh_nav_btn_style(btn, btn.isChecked())

        # ── Rebuild every page so all text/color tokens update ─────────
        current_idx = self._stack.currentIndex()
        _PAGE_BUILDERS = [
            ("Appearance", self._page_appearance),
            ("Accounts", self._page_accounts),
            ("Sync", self._page_sync),
            ("Security", self._page_security),
            ("Advanced", self._page_advanced),
        ]
        for tab_idx in range(self._stack.count()):
            scroll = self._stack.widget(tab_idx)
            if not scroll:
                continue
            # Update the scroll area's own background too
            scroll.setStyleSheet(f"QScrollArea{{background:{bg};border:none;}}")
            inner = QWidget()
            inner.setAttribute(Qt.WA_StyledBackground, True)
            inner.setStyleSheet(f"background:{bg};")
            pl = QVBoxLayout(inner)
            pl.setContentsMargins(28, 24, 28, 24)
            pl.setSpacing(16)
            _PAGE_BUILDERS[tab_idx][1](pl)
            pl.addStretch()
            # QScrollArea.setWidget() automatically takes ownership of `inner`
            # and deletes the previously set widget – do NOT call deleteLater()
            # on the old widget ourselves; doing so causes a RuntimeError because
            # the underlying C++ object is already gone.
            scroll.setWidget(inner)
        self._stack.setCurrentIndex(current_idx)

    # ── Appearance ─────────────────────────────────────────────────────
    def _page_appearance(self, ly):
        ly.addWidget(
            QLabel(
                "Appearance",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )

        # Theme
        tc = CardWidget()
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(16, 16, 16, 16)
        tl.setSpacing(12)
        tl.addWidget(
            QLabel(
                "Color Theme",
                styleSheet=f"font-size:13px;font-weight:600;color:{C('text_secondary')};",
            )
        )
        tr = QHBoxLayout()
        tr.setSpacing(10)

        # Explicit text color so it's legible on both dark AND light themes
        self._dark_btn = QPushButton("  Dark")
        self._light_btn = QPushButton("  Light")
        for b, t in ((self._dark_btn, "dark"), (self._light_btn, "light")):
            b.setCheckable(True)
            b.setChecked(ThemeManager.theme() == t)
            b.setMinimumHeight(40)
            active = ThemeManager.theme() == t
            b.setStyleSheet(
                f"QPushButton{{background:{'#1e293b' if t=='dark' else '#f1f5f9'};"
                f"color:{'#f8fafc' if t=='dark' else '#0f172a'};"
                f"border:2px solid {C('accent') if active else C('border')};"
                f"border-radius:8px;font-weight:600;font-size:13px;}}"
                f"QPushButton:hover{{border-color:{C('accent')};}}"
            )
            b.clicked.connect(lambda _, v=t: self._set_theme(v))
            tr.addWidget(b)
        tr.addStretch()
        tl.addLayout(tr)
        ly.addWidget(tc)

        # Accent
        ac = CardWidget()
        al = QVBoxLayout(ac)
        al.setContentsMargins(16, 16, 16, 16)
        al.setSpacing(12)
        al.addWidget(
            QLabel(
                "Accent Color",
                styleSheet=f"font-size:13px;font-weight:600;color:{C('text_secondary')};",
            )
        )
        pr = QHBoxLayout()
        pr.setSpacing(8)
        for name, hex_col in ACCENT_PRESETS.items():
            b = QPushButton()
            b.setFixedSize(30, 30)
            b.setToolTip(name)
            is_active = ThemeManager.accent() == hex_col
            b.setStyleSheet(
                f"QPushButton{{background:{hex_col};border-radius:15px;"
                f"border:{'3px solid #fff' if is_active else '2px solid transparent'};min-height:0;}}"
                f"QPushButton:hover{{border:3px solid #fff;}}"
            )
            b.clicked.connect(lambda _, c=hex_col: self._set_accent(c))
            pr.addWidget(b)
        pr.addStretch()
        cb = QPushButton("Custom…")
        cb.setProperty("class", "secondary")
        cb.setFixedHeight(34)
        cb.clicked.connect(self._pick_accent)
        pr.addWidget(cb)
        al.addLayout(pr)
        self._accent_preview = QLabel(f"Active: {ThemeManager.accent()}")
        self._accent_preview.setStyleSheet(
            f"font-size:12px;color:{ThemeManager.accent()};font-weight:600;"
        )
        al.addWidget(self._accent_preview)
        ly.addWidget(ac)

        # Background
        bgc = CardWidget()
        bgl = QVBoxLayout(bgc)
        bgl.setContentsMargins(16, 16, 16, 16)
        bgl.setSpacing(12)
        bgl.addWidget(
            QLabel(
                "Background Image",
                styleSheet=f"font-size:13px;font-weight:600;color:{C('text_secondary')};",
            )
        )
        bgr = QHBoxLayout()
        bgr.setSpacing(8)
        cur = SETTINGS.value("bg_image", "")
        self._bg_lbl = QLabel(Path(cur).name if cur else "None")
        self._bg_lbl.setStyleSheet(f"color:{C('text_muted')};font-size:12px;")
        bgr.addWidget(self._bg_lbl, 1)
        chb = QPushButton("Choose")
        chb.setProperty("class", "secondary")
        chb.setFixedHeight(34)
        chb.clicked.connect(self._pick_bg)
        bgr.addWidget(chb)
        clb = QPushButton("Clear")
        clb.setProperty("class", "secondary")
        clb.setFixedHeight(34)
        clb.clicked.connect(self._clear_bg)
        bgr.addWidget(clb)
        bgl.addLayout(bgr)
        opr = QHBoxLayout()
        opr.addWidget(
            QLabel("Opacity:", styleSheet=f"color:{C('text_muted')};font-size:12px;")
        )
        self._op = QSlider(Qt.Horizontal)
        self._op.setRange(2, 30)
        self._op.setValue(int(float(SETTINGS.value("bg_opacity", 0.08)) * 100))
        self._op.valueChanged.connect(
            lambda v: SETTINGS.setValue("bg_opacity", v / 100.0)
        )
        opr.addWidget(self._op)
        bgl.addLayout(opr)
        ly.addWidget(bgc)

        # Apply button
        apb = QPushButton("✓  Apply Theme")
        apb.setMinimumHeight(44)
        apb.setStyleSheet(
            f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C('accent')},stop:1 {C('gradient_end')});"
            f"color:#fff;border:none;border-radius:10px;"
            f"font-size:13px;font-weight:700;letter-spacing:0.3px;}}"
            f"QPushButton:hover{{opacity:0.88;}}"
        )
        apb.clicked.connect(self._apply_appearance)
        ly.addWidget(apb)

    def _set_theme(self, t):
        ThemeManager.set_theme(t)
        is_dark = t == "dark"
        for b, bt in ((self._dark_btn, "dark"), (self._light_btn, "light")):
            active = bt == t
            b.setChecked(active)
            b.setStyleSheet(
                f"QPushButton{{background:{'#1e293b' if bt=='dark' else '#f1f5f9'};"
                f"color:{'#f8fafc' if bt=='dark' else '#0f172a'};"
                f"border:2px solid {C('accent') if active else C('border')};"
                f"border-radius:8px;font-weight:600;font-size:13px;}}"
                f"QPushButton:hover{{border-color:{C('accent')};}}"
            )

    def _set_accent(self, color):
        ThemeManager.set_accent(color)
        self._accent_preview.setText(f"Active: {color}")
        self._accent_preview.setStyleSheet(
            f"font-size:12px;color:{color};font-weight:600;"
        )

    def _pick_accent(self):
        from PyQt5.QtGui import QColor as QC2

        col = QColorDialog.getColor(QC2(ThemeManager.accent()), self)
        if col.isValid():
            self._set_accent(col.name())

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Background Image", "", "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if path:
            SETTINGS.setValue("bg_image", path)
            self._bg_lbl.setText(Path(path).name)

    def _clear_bg(self):
        SETTINGS.setValue("bg_image", "")
        self._bg_lbl.setText("None")

    def _apply_appearance(self):
        """Reapply stylesheet globally so theme + accent changes are visible immediately."""
        apply_theme(QApplication.instance())
        # Rebuild the settings dialog's own background
        self.setStyleSheet(f"background:{C('bg')};")
        # Emit signal so MainWindow._on_theme_changed refreshes all inline styles + icons
        self.theme_changed.emit()
        self._refresh_dialog_styles()
        from alerts import fade_in_widget as fi

        fi(self, 100)

    # ── Accounts ────────────────────────────────────────────────────────
    def _page_accounts(self, ly):
        ly.addWidget(
            QLabel(
                "Accounts",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )
        if not self.accounts:
            ly.addWidget(
                QLabel(
                    "No accounts. Add one from the sidebar.",
                    styleSheet=f"color:{C('text_muted')};font-size:13px;",
                )
            )
            return

        for acc in self.accounts:
            card = CardWidget()
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.addWidget(make_avatar(acc.display_name or acc.email, 40))
            info = QVBoxLayout()
            info.setSpacing(2)
            info.addWidget(
                QLabel(
                    acc.display_name or acc.email,
                    styleSheet=f"font-size:13px;font-weight:700;color:{C('text_primary')};",
                )
            )
            info.addWidget(
                QLabel(acc.email, styleSheet=f"font-size:12px;color:{C('text_muted')};")
            )
            info.addWidget(
                QLabel(
                    acc.provider.title(),
                    styleSheet=f"font-size:10px;font-weight:700;color:{C('accent')};",
                )
            )
            cl.addLayout(info, 1)

            # Use explicit danger btn so text is always readable
            del_btn = _danger_btn("Remove Account")
            del_btn.clicked.connect(lambda _, a=acc: self._remove(a))
            cl.addWidget(del_btn)
            ly.addWidget(card)

        # Apply button
        apb = QPushButton("Done")
        apb.setProperty("class", "secondary")
        apb.setMinimumHeight(40)
        apb.clicked.connect(self.accept)
        ly.addWidget(apb)

    def _remove(self, acc):
        r = QMessageBox.question(
            self,
            "Remove Account",
            f"Remove {acc.email}?\nAll synced emails for this account will be deleted.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            try:
                # Correct engine method is delete_account (sets is_active=0)
                account_svc.delete_account(acc.id)
                # Also purge emails
                db.run("DELETE FROM emails WHERE account_id=?", (acc.id,))
                self.account_changed.emit()
                self.accept()
            except Exception as e:
                log.error(f"Remove: {e}")
                QMessageBox.critical(self, "Error", str(e))

    # ── Sync ────────────────────────────────────────────────────────────
    def _page_sync(self, ly):
        ly.addWidget(
            QLabel(
                "Sync",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )
        card = CardWidget()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(14)

        self._sync_combos = {}
        for label_text, key, choices in [
            (
                "Auto-sync interval",
                "sync_interval",
                [("1 min", 60), ("5 min", 300), ("15 min", 900), ("Manual only", 0)],
            ),
            (
                "Max emails per folder",
                "max_per_folder",
                [("50", 50), ("100", 100), ("200", 200), ("500", 500)],
            ),
        ]:
            row = QHBoxLayout()
            row.addWidget(
                QLabel(
                    label_text,
                    styleSheet=f"color:{C('text_secondary')};font-size:13px;",
                )
            )
            row.addStretch()
            combo = QComboBox()
            combo.setMinimumHeight(36)
            combo.setFixedWidth(140)
            cur = int(SETTINGS.value(key, choices[0][1]))
            for lbl, val in choices:
                combo.addItem(lbl, val)
                if val == cur:
                    combo.setCurrentIndex(combo.count() - 1)
            row.addWidget(combo)
            cl.addLayout(row)
            self._sync_combos[key] = combo
        ly.addWidget(card)

        apb = QPushButton("Apply Sync Settings")
        apb.setMinimumHeight(40)
        apb.clicked.connect(self._apply_sync)
        ly.addWidget(apb)

    def _apply_sync(self):
        for key, combo in self._sync_combos.items():
            SETTINGS.setValue(key, combo.currentData())

    # ── Security ────────────────────────────────────────────────────────
    def _page_security(self, ly):
        ly.addWidget(
            QLabel(
                "Security",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )
        card = CardWidget()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(14)

        row = QHBoxLayout()
        row.addWidget(
            QLabel(
                "Phishing sensitivity",
                styleSheet=f"color:{C('text_secondary')};font-size:13px;",
            )
        )
        row.addStretch()
        self._phish_combo = QComboBox()
        self._phish_combo.setMinimumHeight(36)
        self._phish_combo.setFixedWidth(140)
        for s in ["Low", "Medium", "High"]:
            self._phish_combo.addItem(s)
        cur = SETTINGS.value("phish_sensitivity", "Medium")
        self._phish_combo.setCurrentIndex(max(0, self._phish_combo.findText(cur)))
        row.addWidget(self._phish_combo)
        cl.addLayout(row)

        nrow = QHBoxLayout()
        nrow.addWidget(
            QLabel(
                "Alert on suspicious emails",
                styleSheet=f"color:{C('text_secondary')};font-size:13px;",
            )
        )
        nrow.addStretch()
        self._notify_cb = QCheckBox()
        self._notify_cb.setChecked(SETTINGS.value("security_notify", True, type=bool))
        nrow.addWidget(self._notify_cb)
        cl.addLayout(nrow)
        ly.addWidget(card)

        apb = QPushButton("Apply Security Settings")
        apb.setMinimumHeight(40)
        apb.clicked.connect(self._apply_security)
        ly.addWidget(apb)

    def _apply_security(self):
        SETTINGS.setValue("phish_sensitivity", self._phish_combo.currentText())
        SETTINGS.setValue("security_notify", self._notify_cb.isChecked())

    # ── Advanced ────────────────────────────────────────────────────────
    def _page_advanced(self, ly):
        log_path = APP_DIR / "mailshield.log"
        ly.addWidget(
            QLabel(
                "Advanced",
                styleSheet=f"font-size:20px;font-weight:700;color:{C('text_primary')};",
            )
        )

        lc = CardWidget()
        ll = QVBoxLayout(lc)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(10)
        ll.addWidget(
            QLabel(
                f"Log: {log_path}",
                styleSheet=f"color:{C('text_muted')};font-size:12px;font-family:monospace;",
            )
        )
        import platform as _plt

        _s = _plt.system()
        ob = QPushButton("Open Log Folder")
        ob.setProperty("class", "secondary")
        ob.setFixedHeight(34)
        ob.clicked.connect(
            lambda: (
                os.startfile(str(log_path.parent))
                if _s == "Windows"
                else os.system(
                    f"open '{log_path.parent}'"
                    if _s == "Darwin"
                    else f"xdg-open '{log_path.parent}'"
                )
            )
        )
        ll.addWidget(ob)
        ly.addWidget(lc)

        dc = QFrame()
        dc.setStyleSheet(
            f"QFrame{{background:{C('surface')};border:1px solid {C('danger')}44;border-radius:12px;}}"
        )
        dl = QVBoxLayout(dc)
        dl.setContentsMargins(16, 16, 16, 16)
        dl.setSpacing(10)
        dl.addWidget(
            QLabel(
                "Danger Zone",
                styleSheet=f"font-size:13px;font-weight:700;color:{C('danger')};",
            )
        )
        clear_btn = QPushButton("Clear All Emails & Contacts")
        clear_btn.setStyleSheet(
            f"QPushButton{{background:{C('danger')};color:#fff;min-height:0;"
            f"padding:8px 16px;border-radius:8px;font-weight:600;}}"
        )
        clear_btn.clicked.connect(self._clear_all)
        dl.addWidget(clear_btn)
        ly.addWidget(dc)

    def _clear_all(self):
        r = QMessageBox.question(
            self,
            "Clear All Data",
            "Permanently delete all emails and contacts?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            try:
                db.run("DELETE FROM emails WHERE 1", ())
                db.run("DELETE FROM contacts WHERE 1", ())
                self.account_changed.emit()
                self.accept()
            except Exception as e:
                log.error(f"Clear all: {e}")
                QMessageBox.critical(self, "Error", str(e))


# ── Contact Dialogs ────────────────────────────────────────────────────
class ContactEditDialog(QDialog):
    def __init__(self, parent, user_id, contact=None):
        super().__init__(parent)
        self.user_id = user_id
        self.contact = contact
        self.setWindowTitle("Edit Contact" if contact else "New Contact")
        self.setModal(True)
        self.resize(400, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        fade_in_widget(self, 150)

    def _build(self):
        ly = QVBoxLayout(self)
        ly.setSpacing(14)
        ly.setContentsMargins(28, 28, 28, 24)
        ly.addWidget(
            QLabel(
                "Edit Contact" if self.contact else "Add Contact",
                styleSheet=f"font-size:18px;font-weight:700;color:{C('text_primary')};",
            )
        )
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        def f(ph):
            w = QLineEdit()
            w.setPlaceholderText(ph)
            w.setMinimumHeight(38)
            return w

        self.name_e = f("Full Name")
        self.email_e = f("email@example.com")
        self.phone_e = f("+1 555 000 0000")
        self.company_e = f("Company")

        if self.contact:
            self.name_e.setText(self.contact.name)
            self.email_e.setText(self.contact.email)
            self.phone_e.setText(self.contact.phone)
            self.company_e.setText(self.contact.company)

        for lbl, fld in [
            ("Name *", self.name_e),
            ("Email *", self.email_e),
            ("Phone", self.phone_e),
            ("Company", self.company_e),
        ]:
            form.addRow(lbl, fld)
        ly.addLayout(form)
        ly.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setProperty("class", "secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        ly.addLayout(btns)

    def _save(self):
        name = self.name_e.text().strip()
        em = self.email_e.text().strip()
        if not name or not em:
            QMessageBox.warning(self, "Missing Info", "Name and email required.")
            return
        svc = ContactService(self.user_id)
        if self.contact:
            svc.update(
                self.contact.id,
                name=name,
                email=em,
                phone=self.phone_e.text().strip(),
                company=self.company_e.text().strip(),
            )
        else:
            result = svc.create(
                name=name,
                email=em,
                phone=self.phone_e.text().strip(),
                company=self.company_e.text().strip(),
            )
            if result is None:
                QMessageBox.warning(self, "Duplicate", "Email already in Contacts.")
                return
        self.accept()


class ContactsPanel(QDialog):
    def __init__(self, parent, user_id):
        super().__init__(parent)
        self.user_id = user_id
        self.svc = ContactService(user_id)
        self.setWindowTitle("Contacts")
        self.setModal(True)
        self.resize(780, 580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._selected_contact = None
        self._build()
        self._load()
        fade_in_widget(self, 180)

    def _base_style(self):
        return f"background:{C('bg')};"

    def _build(self):
        self.setStyleSheet(self._base_style())
        main = QHBoxLayout(self)
        main.setSpacing(0)
        main.setContentsMargins(0, 0, 0, 0)

        # ── Left pane ──────────────────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(280)
        left.setStyleSheet(
            f"QFrame{{background:{C('surface')};border-right:1px solid {C('border')};border:none;}}"
        )
        self._left_frame = left
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        # Left header
        lhdr = QFrame()
        lhdr.setFixedHeight(64)
        lhdr.setStyleSheet(
            f"background:{C('surface')};border-bottom:1px solid {C('border')};"
        )
        self._lhdr = lhdr
        lhdrl = QVBoxLayout(lhdr)
        lhdrl.setContentsMargins(16, 10, 16, 10)
        lhdrl.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        # contacts icon + title
        ic = _svg_label("person", 18, C("accent"))
        title_row.addWidget(ic)
        title_lbl = QLabel("Contacts")
        title_lbl.setStyleSheet(
            f"font-size:16px;font-weight:800;color:{C('text_primary')};background:transparent;"
        )
        self._contacts_title_lbl = title_lbl
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        # Close button with SVG
        xb = QPushButton()
        xb.setFixedSize(28, 28)
        xb.setIcon(_svg_icon("close", 14, C("text_muted")))
        from PyQt5.QtCore import QSize

        xb.setIconSize(QSize(14, 14))
        xb.setStyleSheet(
            f"QPushButton{{background:{C('surface_elevated')};border:none;border-radius:14px;"
            f"padding:0;min-height:0;}}"
            f"QPushButton:hover{{background:{C('danger')}22;}}"
        )
        xb.clicked.connect(self.reject)
        self._close_btn = xb
        title_row.addWidget(xb)
        lhdrl.addLayout(title_row)

        # Search field with SVG prefix
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.setContentsMargins(0, 0, 0, 0)
        srch_ic = _svg_label("search", 14, C("text_muted"))
        search_row.addWidget(srch_ic)
        self.search_contacts = QLineEdit()
        self.search_contacts.setPlaceholderText("Search contacts…")
        self.search_contacts.setFixedHeight(28)
        self.search_contacts.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{C('text_primary')};"
            f"font-size:12px;padding:0;}} QLineEdit:focus{{border:none;}}"
        )
        self.search_contacts.textChanged.connect(self._load)
        search_row.addWidget(self.search_contacts)
        srch_wrap = QFrame()
        srch_wrap.setFixedHeight(30)
        srch_wrap.setStyleSheet(
            f"QFrame{{background:{C('surface_elevated')};border:1px solid {C('border')};"
            f"border-radius:8px;}}"
        )
        self._srch_wrap = srch_wrap
        srch_wrap_l = QHBoxLayout(srch_wrap)
        srch_wrap_l.setContentsMargins(8, 0, 8, 0)
        srch_wrap_l.setSpacing(6)
        srch_wrap_l.addWidget(srch_ic)
        srch_wrap_l.addWidget(self.search_contacts)
        lhdrl.addWidget(srch_wrap)
        ll.addWidget(lhdr)

        # Contact list
        self.contact_list = QListWidget()
        self.contact_list.setStyleSheet(
            f"QListWidget{{border:none;background:transparent;outline:none;}}"
            f"QListWidget::item{{padding:0;border:none;background:transparent;}}"
            f"QListWidget::item:selected{{background:transparent;}}"
            f"QListWidget::item:hover{{background:transparent;}}"
        )
        self.contact_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.contact_list.setSpacing(0)
        self.contact_list.itemClicked.connect(self._on_select)
        ll.addWidget(self.contact_list, 1)

        # Left footer – action buttons
        lft = QFrame()
        lft.setFixedHeight(56)
        lft.setStyleSheet(
            f"background:{C('surface')};border-top:1px solid {C('border')};"
        )
        self._lft = lft
        lftl = QHBoxLayout(lft)
        lftl.setContentsMargins(12, 0, 12, 0)
        lftl.setSpacing(8)

        nb = QPushButton()
        nb.setFixedHeight(34)
        nb.setIcon(_svg_icon("add_contact", 15, "#ffffff"))
        nb.setIconSize(QSize(15, 15))
        nb.setText("  New")
        nb.setStyleSheet(
            f"QPushButton{{background:{C('accent')};color:#fff;border:none;border-radius:8px;"
            f"font-size:12px;font-weight:700;padding:0 12px;min-height:0;}}"
            f"QPushButton:hover{{background:{C('accent')}cc;}}"
        )
        nb.clicked.connect(self._new)
        self._new_btn = nb
        lftl.addWidget(nb)

        self.edit_btn = QPushButton()
        self.edit_btn.setFixedHeight(34)
        self.edit_btn.setIcon(_svg_icon("edit", 14, C("text_secondary")))
        self.edit_btn.setIconSize(QSize(14, 14))
        self.edit_btn.setText("  Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.setStyleSheet(
            f"QPushButton{{background:{C('surface_elevated')};color:{C('text')};"
            f"border:1px solid {C('border')};border-radius:8px;font-size:12px;"
            f"font-weight:600;padding:0 12px;min-height:0;}}"
            f"QPushButton:hover{{border-color:{C('accent')};color:{C('accent')};}}"
            f"QPushButton:disabled{{color:{C('text_muted')};border-color:{C('border')};}}"
        )
        self.edit_btn.clicked.connect(self._edit)
        lftl.addWidget(self.edit_btn)

        self.del_btn = QPushButton()
        self.del_btn.setFixedHeight(34)
        self.del_btn.setIcon(_svg_icon("trash", 14, C("danger")))
        self.del_btn.setIconSize(QSize(14, 14))
        self.del_btn.setText("  Delete")
        self.del_btn.setEnabled(False)
        self.del_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('danger')};"
            f"border:1px solid {C('danger')};border-radius:8px;font-size:12px;"
            f"font-weight:600;padding:0 12px;min-height:0;}}"
            f"QPushButton:hover{{background:{C('danger')};color:#fff;}}"
            f"QPushButton:disabled{{color:{C('text_muted')};border-color:{C('border')};}}"
        )
        self.del_btn.clicked.connect(self._delete)
        lftl.addWidget(self.del_btn)
        lftl.addStretch()
        ll.addWidget(lft)
        main.addWidget(left)

        # ── Right pane ──────────────────────────────────────────────────
        self.detail_pane = QFrame()
        self.detail_pane.setStyleSheet(f"background:{C('bg')};border:none;")
        self._detail_pane = self.detail_pane
        self._detail_main_layout = QVBoxLayout(self.detail_pane)
        self._detail_main_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_main_layout.setSpacing(0)
        self._show_empty_detail()
        main.addWidget(self.detail_pane, 1)

    def _show_empty_detail(self):
        self._clear_detail()
        wrap = QWidget()
        wrap.setStyleSheet("background:transparent;")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignCenter)
        wl.setSpacing(12)
        ic = _svg_label("person", 48, C("text_muted") + "66")
        ic.setFixedSize(64, 64)
        pm = _svg_pixmap("person", 48, C("text_muted") + "66")
        bg_lbl = QLabel()
        bg_lbl.setFixedSize(72, 72)
        bg_lbl.setAlignment(Qt.AlignCenter)
        bg_lbl.setStyleSheet(
            f"background:{C('surface_elevated')};border-radius:36px;border:none;"
        )
        inner = QVBoxLayout(bg_lbl)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setAlignment(Qt.AlignCenter)
        ic2 = QLabel()
        ic2.setFixedSize(36, 36)
        ic2.setAlignment(Qt.AlignCenter)
        ic2.setPixmap(_svg_pixmap("person", 36, C("text_muted")))
        inner.addWidget(ic2)
        wl.addWidget(bg_lbl, 0, Qt.AlignHCenter)
        t = QLabel("Select a contact")
        t.setStyleSheet(
            f"color:{C('text_muted')};font-size:15px;font-weight:600;background:transparent;"
        )
        t.setAlignment(Qt.AlignCenter)
        wl.addWidget(t)
        s = QLabel("Click a name on the left to view details")
        s.setStyleSheet(
            f"color:{C('text_muted')};font-size:12px;background:transparent;"
        )
        s.setAlignment(Qt.AlignCenter)
        wl.addWidget(s)
        self._detail_main_layout.addWidget(wrap, 1)

    def _clear_detail(self):
        while self._detail_main_layout.count():
            item = self._detail_main_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_contact_item_widget(self, c) -> QWidget:
        """Build a styled contact row for the list."""
        from utils import make_avatar

        item_w = QWidget()
        item_w.setProperty("contact_id", c.id)
        item_w.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(item_w)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        av = make_avatar(c.name or c.email or "?", 36)
        row.addWidget(av)

        info = QVBoxLayout()
        info.setSpacing(1)
        name_lbl = QLabel(c.name or "(No name)")
        name_lbl.setStyleSheet(
            f"font-size:13px;font-weight:600;color:{C('text_primary')};background:transparent;"
        )
        info.addWidget(name_lbl)
        email_lbl = QLabel(c.email)
        email_lbl.setStyleSheet(
            f"font-size:11px;color:{C('text_muted')};background:transparent;"
        )
        info.addWidget(email_lbl)
        row.addLayout(info, 1)
        return item_w

    def _load(self, _=None):
        self.contact_list.clear()
        q = self.search_contacts.text().strip().lower()
        contacts = [
            c
            for c in self.svc.list_all()
            if not q or q in (c.name or "").lower() or q in (c.email or "").lower()
        ]
        for c in contacts:
            item_w = self._build_contact_item_widget(c)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c.id)
            item.setSizeHint(item_w.sizeHint())
            item.setSizeHint(
                __import__("PyQt5.QtCore", fromlist=["QSize"]).QSize(280, 56)
            )
            self.contact_list.addItem(item)
            self.contact_list.setItemWidget(item, item_w)

    def _on_select(self, item):
        c = self.svc.get(item.data(Qt.UserRole))
        if not c:
            return
        self._selected_contact = c
        self.edit_btn.setEnabled(True)
        self.del_btn.setEnabled(True)
        self._show_contact_detail(c)

    def _show_contact_detail(self, c):
        from utils import make_avatar

        self._clear_detail()

        # Header banner
        hdr = QFrame()
        hdr.setFixedHeight(130)
        hdr.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {C('accent')}18,stop:1 {C('surface_elevated')});"
            f"border-bottom:1px solid {C('border')};"
        )
        hdrl = QVBoxLayout(hdr)
        hdrl.setContentsMargins(28, 20, 28, 16)
        hdrl.setSpacing(8)
        av = make_avatar(c.name or c.email or "?", 52)
        av_row = QHBoxLayout()
        av_row.setSpacing(16)
        av_row.addWidget(av)
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        nl = QLabel(c.name or "(No name)")
        nl.setStyleSheet(
            f"font-size:18px;font-weight:800;color:{C('text_primary')};background:transparent;"
        )
        name_col.addWidget(nl)
        if c.company:
            cl2 = QLabel(c.company)
            cl2.setStyleSheet(
                f"font-size:12px;color:{C('accent')};font-weight:600;background:transparent;"
            )
            name_col.addWidget(cl2)
        av_row.addLayout(name_col, 1)
        hdrl.addLayout(av_row)
        self._detail_main_layout.addWidget(hdr)

        # Info body
        body = QWidget()
        body.setStyleSheet(f"background:{C('bg')};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 20, 24, 20)
        bl.setSpacing(10)

        fields = [
            ("mail", "Email", c.email),
            ("phone", "Phone", c.phone),
            ("building", "Company", c.company),
        ]
        for svg_key, label, val in fields:
            if not val:
                continue
            card = QFrame()
            card.setStyleSheet(
                f"QFrame{{background:{C('surface')};border:1px solid {C('border')};"
                f"border-radius:10px;}}"
            )
            card.setAttribute(Qt.WA_StyledBackground, True)
            cr = QHBoxLayout(card)
            cr.setContentsMargins(14, 12, 14, 12)
            cr.setSpacing(12)
            ic = _svg_label(svg_key, 16, C("accent"))
            cr.addWidget(ic)
            info_col = QVBoxLayout()
            info_col.setSpacing(1)
            lbl_w = QLabel(label)
            lbl_w.setStyleSheet(
                f"font-size:10px;font-weight:700;color:{C('text_muted')};letter-spacing:0.5px;"
                f"background:transparent;"
            )
            info_col.addWidget(lbl_w)
            val_w = QLabel(val)
            val_w.setStyleSheet(
                f"font-size:13px;color:{C('text_primary')};background:transparent;"
            )
            val_w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info_col.addWidget(val_w)
            cr.addLayout(info_col, 1)
            bl.addWidget(card)

        bl.addStretch()
        self._detail_main_layout.addWidget(body, 1)

    def _new(self):
        if ContactEditDialog(self, self.user_id).exec_() == QDialog.Accepted:
            self._load()

    def _edit(self):
        item = self.contact_list.currentItem()
        if not item:
            return
        c = self.svc.get(item.data(Qt.UserRole))
        if c and ContactEditDialog(self, self.user_id, c).exec_() == QDialog.Accepted:
            self._load()
            self._show_contact_detail(c)

    def _delete(self):
        item = self.contact_list.currentItem()
        if not item:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Contact",
                "Delete this contact permanently?",
                QMessageBox.Yes | QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.svc.delete(item.data(Qt.UserRole))
            self._load()
            self._show_empty_detail()
            self.edit_btn.setEnabled(False)
            self.del_btn.setEnabled(False)
