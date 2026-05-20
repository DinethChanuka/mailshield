"""
MailShield – Premium Theme System (v10 – fixed)
Scoped selectors, glassmorphism, background-aware tokens.

Fix: _resolve_font() is now safe to call before QApplication exists.
     apply_theme() refreshes the module-level FONT_FAMILY_* globals so
     every subsequent call (including HTML builders in MainWindow) gets
     the correct system font.
"""

from PyQt5.QtGui import QColor, QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

APP_NAME = "MailShield"
ORG_NAME = "MailShield"
SETTINGS = QSettings(ORG_NAME, APP_NAME)


# ── Font Resolution ──────────────────────────────────────────────────
def _resolve_font() -> str:
    """
    Return the best available system font family name.
    Safe to call even before a QApplication exists – returns a
    generic fallback in that case so the module never aborts on import.
    """
    try:
        db = QFontDatabase()
        families = set(db.families())
        for name in ["SF Pro Text", "Segoe UI", "Helvetica Neue", "Ubuntu"]:
            if name in families:
                return name
        return QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()
    except Exception:
        # No QApplication yet – return a CSS-safe generic family
        return "system-ui"


# Initialised with a safe fallback; refreshed to the real value inside
# apply_theme() once a QApplication is running.
FONT_FAMILY_QT: str = "system-ui"
FONT_FAMILY_CSS: str = "'system-ui', system-ui, sans-serif"

# ── Design Tokens ────────────────────────────────────────────────────
_DARK = {
    "bg": "#080f1e",
    "surface": "#0d1728",
    "surface_elevated": "#162033",
    "border": "#1e2d45",
    "text": "#e8eef7",
    "text_primary": "#f0f5fd",
    "text_secondary": "#9db4d0",
    "text_muted": "#4a6180",
    "success": "#20d264",
    "warning": "#f5a623",
    "danger": "#ff4757",
    "card_hover": "#162033",
    "sidebar": "#070e1c",
    "glass": "rgba(20,26,45,0.72)",
    "glass_strong": "rgba(20,26,45,0.88)",
}
_LIGHT = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "surface_elevated": "#f1f5f9",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "text_primary": "#0f172a",
    "text_secondary": "#334155",
    "text_muted": "#94a3b8",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "card_hover": "#f1f5f9",
    "sidebar": "#f1f5f9",
    "glass": "rgba(255,255,255,0.72)",
    "glass_strong": "rgba(255,255,255,0.88)",
}

ACCENT_PRESETS = {
    "Ocean Blue": "#3b82f6",
    "Emerald": "#10b981",
    "Violet": "#8b5cf6",
    "Rose": "#f43f5e",
    "Amber": "#f59e0b",
    "Cyan": "#06b6d4",
}


class ThemeManager:
    @staticmethod
    def theme() -> str:
        return SETTINGS.value("theme", "dark")

    @staticmethod
    def set_theme(t: str):
        SETTINGS.setValue("theme", t)

    @staticmethod
    def accent() -> str:
        return SETTINGS.value("accent_color", "#3b82f6")

    @staticmethod
    def set_accent(color: str):
        SETTINGS.setValue("accent_color", color)

    @staticmethod
    def palette():
        return _DARK if ThemeManager.theme() == "dark" else _LIGHT

    @staticmethod
    def C(key: str) -> str:
        if key == "accent":
            return ThemeManager.accent()
        if key == "accent_hover":
            return QColor(ThemeManager.accent()).darker(118).name()
        if key == "gradient_start":
            return ThemeManager.accent()
        if key == "gradient_end":
            c = QColor(ThemeManager.accent())
            h, s, v, _ = c.getHsvF()
            return QColor.fromHsvF((h + 0.08) % 1.0, s, min(v * 1.1, 1.0)).name()
        return ThemeManager.palette().get(key, "#000000")


def C(key: str) -> str:
    return ThemeManager.C(key)


def ensure_font_resolved():
    """
    Refresh the module-level font globals.
    Call this after QApplication has been created if you need the
    real system font (apply_theme already does this automatically).
    """
    global FONT_FAMILY_QT, FONT_FAMILY_CSS
    resolved = _resolve_font()
    if resolved != "system-ui":
        FONT_FAMILY_QT = resolved
        FONT_FAMILY_CSS = f"'{FONT_FAMILY_QT}', system-ui, sans-serif"


def apply_theme(app: QApplication):
    # ── Refresh font globals now that QApplication exists ────────────
    global FONT_FAMILY_QT, FONT_FAMILY_CSS
    FONT_FAMILY_QT = _resolve_font()
    FONT_FAMILY_CSS = f"'{FONT_FAMILY_QT}', system-ui, sans-serif"

    font = QFont(FONT_FAMILY_QT, 13)
    app.setFont(font)

    acc = C("accent")
    acch = C("accent_hover")
    bg = C("bg")
    surf = C("surface")
    surfe = C("surface_elevated")
    bdr = C("border")
    txt = C("text")
    muted = C("text_muted")
    hover = C("card_hover")
    danger = C("danger")
    glass = C("glass")
    glass_strong = C("glass_strong")
    sidebar_bg = C("sidebar")

    app.setStyleSheet(
        f"""
    * {{ font-family: {FONT_FAMILY_CSS}; }}
    QMainWindow {{ background: {bg}; }}

    /* ── Scoped panels (use object names) ── */
    QWidget#GlassSidebar {{
        background: {glass};
        border-right: 1px solid {bdr};
    }}

    QWidget#ListPanel {{
        background: {surf};
        border-right: 1px solid {bdr};
    }}

    QWidget#DetailPanel {{
        background: {bg};
    }}

    /* ── General controls ── */
    QPushButton {{
        background: {acc}; color: #fff; border: none; border-radius: 8px;
        padding: 8px 20px; font-weight: 600; font-size: 13px; min-height: 36px;
    }}
    QPushButton:hover {{ background: {acch}; }}
    QPushButton:disabled {{ background: {surfe}; color: {muted}; }}

    QPushButton[class="secondary"] {{
        background: {surfe}; color: {txt}; border: 1px solid {bdr};
    }}
    QPushButton[class="secondary"]:hover {{ background: {hover}; }}
    QPushButton[class="ghost"] {{
        background: transparent; color: {txt}; border: none;
    }}
    QPushButton[class="ghost"]:hover {{ background: {hover}; }}
    QPushButton[class="danger-outline"] {{
        background: transparent; color: {danger}; border: 1px solid {danger};
    }}
    QPushButton[class="danger-outline"]:hover {{
        background: {danger}; color: #fff;
    }}

    /* Inputs */
    QLineEdit, QTextEdit, QComboBox {{
        background: {surf}; border: 1px solid {bdr};
        border-radius: 8px; padding: 8px 12px; color: {txt}; font-size: 13px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border: 1.5px solid {acc}; }}
    QComboBox {{ min-height: 36px; padding-right: 24px; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {surf}; border: 1px solid {bdr};
        selection-background-color: {hover}; color: {txt};
        border-radius: 8px; padding: 4px;
    }}

    /* List widget – email list only */
    QListWidget#EmailList {{
        background: transparent; border: none; outline: none;
    }}
    QListWidget#EmailList::item {{
        background: transparent; border-bottom: 1px solid {bdr}; padding: 0;
    }}
    QListWidget#EmailList::item:selected {{ background: {hover}; }}
    QListWidget#EmailList::item:hover {{ background: {surfe}; }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: transparent; width: 8px;
    }}
    QScrollBar::handle:vertical {{
        background: {bdr}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {muted}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent; height: 8px;
    }}
    QScrollBar::handle:horizontal {{
        background: {bdr}; border-radius: 4px; min-width: 24px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* Misc */
    QSplitter::handle {{ background: {bdr}; width: 1px; height: 1px; }}
    QToolTip {{
        background: {surfe}; color: {txt}; border: 1px solid {bdr};
        border-radius: 6px; padding: 6px 10px; font-size: 12px;
    }}
    QToolButton {{
        background: transparent; border: none; border-radius: 8px;
        padding: 6px 12px; color: {txt};
    }}
    QToolButton:hover   {{ background: {hover}; }}
    QToolButton:checked {{ background: {acc}1A; color: {acc}; font-weight: 700; }}
    QTabWidget::pane {{ border: 1px solid {bdr}; border-radius: 8px; margin-top: -1px; }}
    QTabBar::tab {{
        background: transparent; border: none; padding: 8px 16px;
        color: {muted}; font-size: 13px;
    }}
    QTabBar::tab:selected {{ color: {acc}; border-bottom: 2px solid {acc}; font-weight: 600; }}
    QTabBar::tab:hover   {{ color: {txt}; }}
    QGroupBox {{
        border: 1px solid {bdr}; border-radius: 10px;
        margin-top: 16px; padding-top: 12px; color: {txt};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; subcontrol-position: top left;
        padding: 0 8px; color: {muted}; font-size: 11px;
        font-weight: 700; letter-spacing: 0.5px;
    }}
    """
    )
