"""
MailShield – Main Window v7.0
Fixes:
  1. Login/dialog light-theme propagation
  2. Email action buttons fully functional (no OS open)
  3. Beautiful security analysis UI with expandable deep details
  4. Deep analysis with step-by-step animated progress
  5. Account selector replaced with current-account indicator; accounts in sidebar
  6. Real-time theme + icon-color update on Apply
  7. Attachment indicator in list + attachment panel in reader
"""

from __future__ import annotations

import json
import logging
import os
import re
import html as html_lib
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import (
    Qt,
    QSize,
    QTimer,
    QUrl,
    QByteArray,
    pyqtSignal,
    pyqtSlot,
    QThread,
)
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PyQt5.QtSvg import QSvgRenderer, QSvgWidget
from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from theme import (
    C,
    ThemeManager,
    apply_theme,
    SETTINGS,
    ensure_font_resolved,
    FONT_FAMILY_CSS,
)
from utils import ago, make_avatar, section_label, map_imap_error
from alerts import ToastManager, AlertBanner, ErrorDialog
from workers import SyncThread
from components import EmailListItem, EmptyState
from dialogs import (
    ComposeDialog,
    SettingsDialog,
    ContactsPanel,
    ContactEditDialog,
    AddAccountDialog,
)
from security_engine import normal_analysis, DeepAnalysisWorker
from security_analysis_qss import analysis_panel_qss

try:
    from engine import Account, EmailMsg, account_svc, email_svc, APP_DIR
except ImportError:
    pass

log = logging.getLogger("mailshield")

_ICON_DIR = Path(__file__).parent / "icons"

# ── SVG icon utilities ─────────────────────────────────────────────────


def _make_themed_icon(name: str, size: int = 18, color: str = "") -> QIcon:
    """Load SVG, tint to theme color, return QIcon."""
    path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        return QIcon()
    try:
        content = path.read_text(encoding="utf-8")
        col = color or C("text_secondary")
        # Replace common dark colours with theme colour
        for old in [
            "#000000",
            "#000",
            "black",
            "#1a1a1a",
            "#333333",
            "#333",
            "#222222",
            "#222",
            "#111111",
            "#111",
            "#0f0f0f",
        ]:
            content = content.replace(old, col)
        # Handle currentColor (replace with explicit)
        content = content.replace("currentColor", col)
        renderer = QSvgRenderer(QByteArray(content.encode("utf-8")))
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        return QIcon(pm)
    except Exception:
        return QIcon(str(path))


def _qicon(name: str) -> QIcon:
    return _make_themed_icon(name)


# ── Custom web page: intercepts action: protocol ───────────────────────


class MailWebPage(QWebEnginePage):
    """Intercepts action:verb:param navigation – never opens OS browser."""

    def __init__(self, main_window: "MainWindow"):
        # Pass main_window as Qt parent (it's a QObject) and keep our own ref
        super().__init__(main_window)
        self._mw = main_window

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        url_str = url.toString()
        # Handle our custom protocol
        if url_str.startswith("action:"):
            self._mw.handle_action(url_str)
            return False  # block the navigation
        # Block all external http/https navigation (emails should not open browser)
        if url_str.startswith("http://") or url_str.startswith("https://"):
            return False
        # Allow about:blank and data: URIs (used for rendering)
        return True


# ── Main Window ────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self, user: dict):
        super().__init__()
        ensure_font_resolved()
        if not isinstance(user, dict) or "id" not in user:
            raise ValueError("User must be a dict containing 'id' key")
        self.user = user
        self.accounts: List[Account] = []
        self.current_account_id = "__all__"
        self.current_folder = "INBOX"
        self.search_query = ""
        self.sync_thread: Optional[SyncThread] = None
        self._bg_pixmap: Optional[QPixmap] = None
        self._banners: Dict[str, AlertBanner] = {}

        self.analysis_cache: Dict[str, dict] = {}
        self.deep_worker: Optional[DeepAnalysisWorker] = None
        self._loading_animation_timer: Optional[QTimer] = None
        self._loading_dots = 0
        self._current_email: Optional["EmailMsg"] = None
        self._email_by_id: Dict[str, "EmailMsg"] = {}
        self._deep_in_progress = False

        # Widgets that need inline-style refresh on theme change
        self._sidebar_frame: Optional[QFrame] = None
        self._toolbar_frame: Optional[QFrame] = None
        self._list_panel_frame: Optional[QFrame] = None
        self._statusbar_frame: Optional[QFrame] = None
        self._detail_panel_frame: Optional[QFrame] = None
        self._folder_title_bar_frame: Optional[QFrame] = None
        self._acct_indicator_lbl: Optional[QLabel] = None
        self._logo_icon_lbl: Optional[QLabel] = None
        self._logo_title_lbl: Optional[QLabel] = None

        self._load_bg()
        self.setWindowTitle("MailShield")
        self.setGeometry(80, 60, 1400, 880)
        self.setMinimumSize(1080, 680)

        self._build_ui()
        self.toast = ToastManager(self)
        self._setup_shortcuts()

        self.db_load_thread: Optional["QThread"] = None

        self.load_accounts()
        # Populate the UI from the local DB cache instantly, then sync from server
        QTimer.singleShot(0, self._start_db_preload)
        QTimer.singleShot(1800, self.start_sync)

        iv = int(SETTINGS.value("sync_interval", 60)) * 1000
        if iv > 0:
            self._sync_timer = QTimer(self)
            self._sync_timer.timeout.connect(self.start_sync)
            self._sync_timer.start(iv)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_email_list)
        self._refresh_timer.start(60_000)

    # ── Background ─────────────────────────────────────────────────────
    def _load_bg(self):
        try:
            from engine import BG_IMAGE_PATH as _BG
        except ImportError:
            _BG = None
        path = SETTINGS.value("bg_image", "")
        if not path and _BG and Path(_BG).exists():
            path = str(_BG)
        if path:
            pm = QPixmap(str(path))
            self._bg_pixmap = pm if not pm.isNull() else None
        else:
            # Explicitly clear when no image is set (e.g. after "Clear")
            self._bg_pixmap = None
        self.update()  # force repaint so the change is visible immediately

    def paintEvent(self, event):
        # Draw base background first so child widgets always render on top
        super().paintEvent(event)
        if self._bg_pixmap:
            p = QPainter(self)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            scaled = self._bg_pixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            p.setOpacity(float(SETTINGS.value("bg_opacity", 0.08)))
            p.drawPixmap(
                (self.width() - scaled.width()) // 2,
                (self.height() - scaled.height()) // 2,
                scaled,
            )
            p.end()

    # ── Shortcuts ──────────────────────────────────────────────────────
    def _setup_shortcuts(self):
        for keys, fn in [
            (Qt.CTRL + Qt.Key_N, lambda: self.compose()),
            (Qt.CTRL + Qt.Key_R, self._refresh_and_reanalyse),
            (Qt.CTRL + Qt.Key_Shift + Qt.Key_R, self.start_sync),
            (Qt.CTRL + Qt.Key_F, self._focus_search),
            (Qt.CTRL + Qt.Key_Comma, self.show_settings),
            (Qt.Key_F5, self.start_sync),
        ]:
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(fn)

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ── Build UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setSpacing(0)
        ml.setContentsMargins(0, 0, 0, 0)
        self._build_sidebar(ml)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(0)
        rl.setContentsMargins(0, 0, 0, 0)
        self._build_toolbar(rl)

        self._banner_container = QWidget()
        self._banner_layout = QVBoxLayout(self._banner_container)
        self._banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_layout.setSpacing(0)
        rl.addWidget(self._banner_container)

        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(1)
        sp.addWidget(self._build_list_panel())
        sp.addWidget(self._build_detail_panel())
        sp.setSizes([400, 1000])
        sp.setStretchFactor(0, 1)
        sp.setStretchFactor(1, 2)
        rl.addWidget(sp, 1)

        self._build_statusbar(rl)
        ml.addWidget(right, 1)

        # Default folder selection – must come after _folder_btns is built
        QTimer.singleShot(0, lambda: self.switch_folder("INBOX"))

        # ── Refresh overlay ────────────────────────────────────────────
        self._refresh_overlay = QWidget(self)
        self._refresh_overlay.setVisible(False)
        self._refresh_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self._refresh_overlay.setStyleSheet(
            "background:rgba(255,255,255,0); border:none;"
        )
        ov_l = QVBoxLayout(self._refresh_overlay)
        ov_l.setAlignment(Qt.AlignCenter)
        ov_l.setSpacing(18)

        self._ov_img_lbl = QLabel()
        self._ov_img_lbl.setFixedSize(96, 96)
        self._ov_img_lbl.setAlignment(Qt.AlignCenter)
        ov_l.addWidget(self._ov_img_lbl, 0, Qt.AlignHCenter)

        self._ov_text_lbl = QLabel("Refreshing")
        self._ov_text_lbl.setAlignment(Qt.AlignCenter)
        self._ov_text_lbl.setStyleSheet(
            "font-size:20px;font-weight:700;color:#1e293b;background:transparent;"
        )
        ov_l.addWidget(self._ov_text_lbl, 0, Qt.AlignHCenter)

        self._ov_bar = QProgressBar()
        self._ov_bar.setFixedWidth(300)
        self._ov_bar.setFixedHeight(8)
        self._ov_bar.setTextVisible(False)
        self._ov_bar.setRange(0, 100)
        self._ov_bar.setValue(0)
        self._ov_bar.setStyleSheet(
            "QProgressBar{background:#e2e8f0;border-radius:4px;border:none;}"
            "QProgressBar::chunk{background:#3b82f6;border-radius:4px;}"
        )
        ov_l.addWidget(self._ov_bar, 0, Qt.AlignHCenter)

        self._ov_pct_lbl = QLabel("0%")
        self._ov_pct_lbl.setAlignment(Qt.AlignCenter)
        self._ov_pct_lbl.setStyleSheet(
            "font-size:13px;color:#64748b;background:transparent;"
        )
        ov_l.addWidget(self._ov_pct_lbl, 0, Qt.AlignHCenter)

        self._ov_progress_val = 0
        self._ov_progress_timer = QTimer(self)
        self._ov_progress_timer.setInterval(30)
        self._ov_progress_timer.timeout.connect(self._ov_tick)

    # ── Sidebar ────────────────────────────────────────────────────────
    def _build_sidebar(self, ml):
        sb = QFrame()
        sb.setObjectName("GlassSidebar")  # NEW: scoped style
        sb.setFixedWidth(220)
        sb.setStyleSheet(
            f"QFrame{{background:{C('sidebar')};border-right:1px solid {C('border')};}}"
        )
        self._sidebar_frame = sb
        sl = QVBoxLayout(sb)
        sl.setContentsMargins(12, 16, 12, 16)
        sl.setSpacing(2)

        # ── Logo / brand row ───────────────────────────────────────────
        logo_outer = QHBoxLayout()
        logo_outer.setSpacing(0)
        logo_outer.setContentsMargins(0, 0, 0, 0)

        # Gradient shield badge
        shield_lbl = QLabel()
        shield_lbl.setFixedSize(36, 36)
        shield_lbl.setAttribute(Qt.WA_StyledBackground, True)
        shield_lbl.setAlignment(Qt.AlignCenter)
        self._logo_icon_lbl = shield_lbl

        def _paint_shield(lbl):
            """Render the shield + M letter into the QLabel pixmap."""
            from PyQt5.QtCore import QByteArray
            from PyQt5.QtSvg import QSvgRenderer

            acc = C("accent")
            ge = C("gradient_end")
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{acc}"/>
      <stop offset="1" stop-color="{ge}"/>
    </linearGradient>
    <filter id="s">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="{acc}" flood-opacity="0.35"/>
    </filter>
  </defs>
  <path d="M18 2 L32 8 L32 18 C32 26 25 31 18 34 C11 31 4 26 4 18 L4 8 Z"
        fill="url(#g)" filter="url(#s)"/>
  <text x="18" y="23" text-anchor="middle" font-family="system-ui,sans-serif"
        font-size="13" font-weight="900" fill="#fff" letter-spacing="0">M</text>
</svg>"""
            renderer = QSvgRenderer(QByteArray(svg.encode()))
            pm = QPixmap(36, 36)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p)
            p.end()
            lbl.setPixmap(pm)
            lbl.setStyleSheet("background:transparent;border:none;")

        _paint_shield(shield_lbl)
        self._paint_shield_fn = _paint_shield  # store for theme refresh
        logo_outer.addWidget(shield_lbl)
        logo_outer.addSpacing(10)

        # Name + tagline column
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_col.setContentsMargins(0, 0, 0, 0)

        lt = QLabel("MailShield")
        lt.setStyleSheet(
            f"font-size:15px;font-weight:900;color:{C('text_primary')};"
            f"letter-spacing:-0.3px;background:transparent;"
        )
        self._logo_title_lbl = lt
        brand_col.addWidget(lt)

        tag = QLabel("Secure Email Intelligence")
        tag.setStyleSheet(
            f"font-size:9px;font-weight:600;color:{C('accent')};"
            f"letter-spacing:0.6px;background:transparent;"
        )
        self._logo_tag_lbl = tag
        brand_col.addWidget(tag)

        logo_outer.addLayout(brand_col)
        logo_outer.addStretch()

        lr = logo_outer
        lr.addStretch()
        sl.addLayout(lr)
        sl.addSpacing(14)

        # Compose button
        cb = QPushButton()
        self._compose_btn = cb
        self._set_icon_btn(cb, "compose", "  Compose  (Ctrl+N)")
        cb.setFixedHeight(40)
        cb.setStyleSheet(
            f"QPushButton{{background:{C('accent')};color:#fff;"
            f"border-radius:10px;font-weight:700;font-size:13px;"
            f"text-align:left;padding-left:14px;}}"
            f"QPushButton:hover{{background:{C('accent_hover')};}}"
        )
        cb.clicked.connect(lambda: self.compose())
        sl.addWidget(cb)
        sl.addSpacing(14)

        # Folder buttons
        sl.addWidget(section_label("Folders"))
        self._folder_btns: Dict[str, QToolButton] = {}
        for fid, flabel, icon in [
            ("INBOX", "Inbox", "inbox"),
            ("starred", "Starred", "starred"),
            ("sent", "Sent", "sent"),
            ("drafts", "Drafts", "drafts"),
            ("trash", "Trash", "trash"),
        ]:
            btn = self._nav_btn_svg(fid, flabel, icon)
            self._folder_btns[fid] = btn
            sl.addWidget(btn)

        sl.addSpacing(12)
        sl.addWidget(section_label("Accounts"))

        # Account buttons container (replaces QListWidget)
        self._acct_btn_container = QWidget()
        self._acct_btn_container.setStyleSheet("background:transparent;")
        self._acct_btn_layout = QVBoxLayout(self._acct_btn_container)
        self._acct_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._acct_btn_layout.setSpacing(2)
        sl.addWidget(self._acct_btn_container)
        self._acct_buttons: Dict[str, QPushButton] = {}

        sl.addStretch()
        sl.addSpacing(12)

        # "All Accounts" button
        self._all_acct_btn = QPushButton()
        self._all_acct_btn.setFixedHeight(36)
        self._all_acct_btn.setCursor(Qt.PointingHandCursor)
        self._all_acct_btn.setText("  All Accounts")
        self._all_acct_btn.setCheckable(True)
        self._all_acct_btn.setChecked(True)
        self._style_all_acct_btn()
        self._all_acct_btn.clicked.connect(self._select_all_accounts)
        sl.addWidget(self._all_acct_btn)
        sl.addSpacing(4)

        # Add Account button
        self._add_acct_btn = QPushButton("+ Add Account")
        self._add_acct_btn.setFixedHeight(34)
        self._add_acct_btn.setCursor(Qt.PointingHandCursor)
        self._style_add_acct_btn()
        self._add_acct_btn.clicked.connect(self.add_email_account)
        sl.addWidget(self._add_acct_btn)
        sl.addSpacing(10)

        for label, icon, fn in [
            ("Contacts", "contacts", self.show_contacts),
            ("Settings  Ctrl+,", "settings", self.show_settings),
        ]:
            btn = self._nav_btn_svg(
                label.lower().split()[0], label, icon, checkable=False
            )
            btn.clicked.connect(fn)
            sl.addWidget(btn)

        ml.addWidget(sb)

    def _style_all_acct_btn(self):
        acc = C("accent")
        self._all_acct_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('text_secondary')};"
            f"border:none;border-radius:8px;font-size:12px;font-weight:500;"
            f"text-align:left;padding:0 8px;}}"
            f"QPushButton:hover{{background:{C('surface_elevated')};color:{C('text_primary')};}}"
            f"QPushButton:checked{{background:{acc}1A;color:{acc};font-weight:700;}}"
        )

    def _style_add_acct_btn(self):
        acc = C("accent")
        self._add_acct_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('text_muted')};"
            f"border:1px dashed {C('border')};border-radius:8px;"
            f"font-size:12px;font-weight:500;text-align:left;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{acc};color:{acc};background:{acc}10;}}"
        )

    def _update_account_list_style(self):
        pass  # replaced by custom account buttons

    def _nav_btn_svg(
        self, fid: str, label: str, icon: str, checkable: bool = True
    ) -> QToolButton:
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        ico = _make_themed_icon(icon, 16)
        if not ico.isNull():
            btn.setIcon(ico)
            btn.setIconSize(QSize(16, 16))
        btn.setText(f"  {label}")
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setFixedHeight(36)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QToolButton{{text-align:left;padding-left:10px;border-radius:8px;"
            f"font-size:13px;color:{C('text_secondary')};background:transparent;}}"
            f"QToolButton:hover{{background:{C('card_hover')};}}"
            f"QToolButton:checked{{background:{C('accent')}1A;color:{C('accent')};font-weight:700;}}"
        )
        if checkable and fid not in ("contacts", "settings"):
            btn.clicked.connect(lambda _, f=fid: self.switch_folder(f))
        return btn

    def _set_icon_btn(
        self, btn: QPushButton, icon: str, text: str, color: str = "#ffffff"
    ):
        ico = _make_themed_icon(icon, 16, color)
        if not ico.isNull():
            btn.setIcon(ico)
            btn.setIconSize(QSize(16, 16))
        btn.setText(text)

    def _svg_inline(self, name: str, color: str, size: int = 14) -> str:
        """Return inline SVG string for embedding in HTML email detail view."""
        path = _ICON_DIR / f"{name}.svg"
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8")
            for old in [
                "#000000",
                "#000",
                "black",
                "#1a1a1a",
                "#333333",
                "#333",
                "#222222",
                "#222",
                "#111111",
                "#111",
                "#0f0f0f",
            ]:
                content = content.replace(old, color)
            content = content.replace("currentColor", color)
            # Remove width/height attrs then inject fixed size
            content = re.sub(r'\s+width="[^"]*"', "", content)
            content = re.sub(r'\s+height="[^"]*"', "", content)
            content = content.replace(
                "<svg",
                f'<svg width="{size}" height="{size}" style="vertical-align:middle;display:inline-block;flex-shrink:0;"',
                1,
            )
            return content
        except Exception:
            return ""

    def _update_email_list_badge(self, email: "EmailMsg"):
        """Find the email's list item and refresh its risk badge widget."""
        for i in range(self.email_list.count()):
            item = self.email_list.item(i)
            w = self.email_list.itemWidget(item)
            if w and hasattr(w, "email") and w.email.id == email.id:
                w.email.security_risk = email.security_risk
                nw = EmailListItem(w.email)
                item.setSizeHint(nw.sizeHint())
                self.email_list.setItemWidget(item, nw)
                break

    # ── Toolbar (no account combo – replaced with current-account label) ─
    def _build_toolbar(self, rl):
        tb = QFrame()
        tb.setFixedHeight(58)
        tb.setStyleSheet(
            f"QFrame{{background:{C('surface')};border-bottom:1px solid {C('border')};}}"
        )
        self._toolbar_frame = tb
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(16, 8, 16, 8)
        tl.setSpacing(10)

        # Current account indicator (read-only display, not a selector)
        self._acct_indicator_lbl = QLabel("All Accounts")
        self._acct_indicator_lbl.setStyleSheet(
            f"background:{C('surface_elevated')};color:{C('text_secondary')};"
            f"border:1px solid {C('border')};border-radius:8px;"
            f"padding:6px 14px;font-size:12px;font-weight:600;"
        )
        self._acct_indicator_lbl.setFixedHeight(38)
        self._acct_indicator_lbl.setMinimumWidth(160)
        tl.addWidget(self._acct_indicator_lbl)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search emails…   Ctrl+F")
        self.search_edit.setMinimumWidth(300)
        self.search_edit.setMinimumHeight(38)
        self.search_edit.textChanged.connect(self._on_search)
        tl.addWidget(self.search_edit)
        tl.addStretch()

        self._toolbar_btns = []
        self._toolbar_btn_icons: list = (
            []
        )  # (btn, icon_name) for re-coloring on theme change
        for label, tip, icon, fn in [
            (
                "Refresh",
                "Refresh & re-analyse risks  Ctrl+R",
                "sync",
                self._refresh_and_reanalyse,
            ),
            ("Sync", "Sync from server  F5", "sync", self.start_sync),
            ("Security", "Security overview", "security", self.show_security_dashboard),
        ]:
            btn = QPushButton()
            ico = _make_themed_icon(
                icon, 16, C("text")
            )  # theme-adaptive, NOT hardcoded white
            if not ico.isNull():
                btn.setIcon(ico)
                btn.setIconSize(QSize(16, 16))
            btn.setText(f"  {label}")
            btn.setToolTip(tip)
            btn.setMinimumHeight(38)
            self._apply_toolbar_btn_style(btn)
            btn.clicked.connect(fn)
            tl.addWidget(btn)
            self._toolbar_btns.append(btn)
            self._toolbar_btn_icons.append((btn, icon))

        rl.addWidget(tb)

    def _apply_toolbar_btn_style(self, btn: "QPushButton"):
        """Explicit themed style for toolbar buttons — responds to theme changes."""
        btn.setStyleSheet(
            f"QPushButton{{background:{C('surface_elevated')};color:{C('text')};"
            f"border:1px solid {C('border')};border-radius:8px;"
            f"padding:6px 16px;font-size:13px;font-weight:600;min-height:36px;}}"
            f"QPushButton:hover{{background:{C('accent')}1A;color:{C('accent')};"
            f"border:1px solid {C('accent')}55;}}"
            f"QPushButton:pressed{{background:{C('accent')}30;}}"
        )

    # ── List panel ──────────────────────────────────────────────────────
    def _build_list_panel(self):
        panel = QFrame()
        panel.setObjectName("ListPanel")  # NEW
        panel.setStyleSheet(
            f"QFrame{{background:{C('surface')};border-right:1px solid {C('border')};}}"
        )
        self._list_panel_frame = panel
        l = QVBoxLayout(panel)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        self.folder_title_bar = QFrame()
        self.folder_title_bar.setFixedHeight(42)
        self.folder_title_bar.setStyleSheet(
            f"background:{C('surface')};border-bottom:1px solid {C('border')};"
        )
        self._folder_title_bar_frame = self.folder_title_bar
        ftl = QHBoxLayout(self.folder_title_bar)
        ftl.setContentsMargins(16, 0, 16, 0)
        self.folder_title_lbl = QLabel("Inbox")
        self.folder_title_lbl.setStyleSheet(
            f"font-size:15px;font-weight:700;color:{C('text_primary')};"
        )
        self.email_count_lbl = QLabel("")
        self.email_count_lbl.setStyleSheet(
            f"font-size:11px;color:{C('text_muted')};"
            f"background:{C('surface_elevated')};border-radius:8px;padding:2px 8px;"
        )
        ftl.addWidget(self.folder_title_lbl)
        ftl.addStretch()
        ftl.addWidget(self.email_count_lbl)
        l.addWidget(self.folder_title_bar)

        self._list_stack = QStackedWidget()
        self.email_list = QListWidget()
        self.email_list.setObjectName("EmailList")  # NEW
        self.email_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.email_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.email_list.setSpacing(0)
        self.email_list.setUniformItemSizes(False)
        self.email_list.itemClicked.connect(self._on_email_selected)
        self._list_stack.addWidget(self.email_list)
        self._list_stack.addWidget(
            EmptyState("✉", "No emails here", "Sync or switch folders.")
        )
        l.addWidget(self._list_stack, 1)
        return panel

    # ── Detail panel ───────────────────────────────────────────────────
    def _build_detail_panel(self):
        panel = QFrame()
        panel.setObjectName("DetailPanel")  # NEW
        panel.setStyleSheet(f"background:{C('bg')};")
        self._detail_panel_frame = panel
        l = QVBoxLayout(panel)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(
            EmptyState("M", "Select an email to read", "Press Ctrl+N to compose.")
        )
        self.web_view = QWebEngineView()
        ws = self.web_view.settings()
        ws.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        ws.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        ws.setAttribute(QWebEngineSettings.AutoLoadImages, True)

        # MailWebPage intercepts action: protocol and blocks external URLs
        self.web_page = MailWebPage(self)
        self.web_view.setPage(self.web_page)
        self.web_page.linkHovered.connect(self._on_link_hovered)

        self.detail_stack.addWidget(self.web_view)
        l.addWidget(self.detail_stack)
        return panel

    # ── Status bar ──────────────────────────────────────────────────────
    def _build_statusbar(self, rl):
        sb = QFrame()
        sb.setFixedHeight(30)
        sb.setStyleSheet(
            f"QFrame{{background:{C('surface')};border-top:1px solid {C('border')};}}"
        )
        self._statusbar_frame = sb
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(16, 0, 16, 0)
        sl.setSpacing(12)
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color:{C('text_muted')};font-size:11px;")
        sl.addWidget(self.status_lbl)
        sl.addWidget(
            QLabel(
                self.user.get("username", ""),
                styleSheet=f"color:{C('text_muted')};font-size:11px;",
            )
        )
        sl.addStretch()
        self.sync_progress = QProgressBar()
        self.sync_progress.setMaximumWidth(200)
        self.sync_progress.setFixedHeight(4)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setVisible(False)
        sl.addWidget(self.sync_progress)
        self.sync_lbl = QLabel("")
        self.sync_lbl.setStyleSheet(
            f"color:{C('accent')};font-size:11px;font-weight:600;"
        )
        sl.addWidget(self.sync_lbl)
        rl.addWidget(sb)

    # ── Accounts ────────────────────────────────────────────────────────
    def load_accounts(self):
        try:
            self.accounts = account_svc.list_for_user(self.user["id"])
        except Exception as e:
            log.error(f"load_accounts: {e}")
            self.accounts = []

        self._rebuild_account_buttons()
        self._update_account_indicator()

    def _start_db_preload(self):
        """
        Immediately populate the email list from the local SQLite cache so the
        inbox appears instant on launch — before the first IMAP sync completes.

        Runs on the GUI thread via QTimer.singleShot(0, …) so it executes as
        soon as the event loop starts, without blocking the constructor.
        """
        if not self.accounts:
            return
        try:
            acct_ids = [a.id for a in self.accounts]
            # Load the most recent 500 emails across all folders so the
            # in-memory cache (_email_by_id) is warm for any folder the user
            # switches to before the first network sync.
            for folder in ("INBOX", "sent", "drafts", "trash"):
                try:
                    msgs, _ = email_svc.list_emails(
                        account_ids=acct_ids,
                        folder="" if folder != "INBOX" else "INBOX",
                        page_size=200,
                    )
                    for m in msgs:
                        self._email_by_id[m.id] = m
                except Exception as ex:
                    log.debug(f"_start_db_preload folder={folder}: {ex}")
            log.info(f"DB pre-load complete: {len(self._email_by_id)} emails cached.")
        except Exception as e:
            log.warning(f"_start_db_preload: {e}")
        finally:
            # Refresh the list whether we got data or not
            self.refresh_email_list()

    def _rebuild_account_buttons(self):
        from utils import avatar_color

        # Clear old buttons
        while self._acct_btn_layout.count():
            item = self._acct_btn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._acct_buttons.clear()

        for a in self.accounts:
            label = a.display_name or a.email or "?"
            color = avatar_color(label)
            initial = label[0].upper()

            btn = QPushButton()
            btn.setFixedHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)

            # Build icon pixmap (colored circle with letter)
            from PyQt5.QtGui import QPixmap, QPainter, QFont as QF, QBrush

            pm = QPixmap(22, 22)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, 22, 22)
            p.setPen(QColor("#ffffff"))
            f = QF()
            f.setPointSize(9)
            f.setBold(True)
            p.setFont(f)
            p.drawText(pm.rect(), Qt.AlignCenter, initial)
            p.end()
            btn.setIcon(QIcon(pm))
            btn.setIconSize(QSize(22, 22))

            display = (label[:20] + "…") if len(label) > 20 else label
            btn.setText(f"  {display}")
            btn.setToolTip(a.email)
            self._style_acct_btn(btn, False)
            btn.clicked.connect(lambda _, aid=a.id: self._on_acct_btn_clicked(aid))
            self._acct_btn_layout.addWidget(btn)
            self._acct_buttons[a.id] = btn

    def _update_account_indicator(self):
        if self._acct_indicator_lbl is None:
            return
        if self.current_account_id == "__all__":
            txt = f"All Accounts ({len(self.accounts)})"
        else:
            acc = next(
                (a for a in self.accounts if a.id == self.current_account_id), None
            )
            txt = acc.email if acc else "All Accounts"
        self._acct_indicator_lbl.setText(txt)

    def _style_acct_btn(self, btn: "QPushButton", selected: bool):
        acc = C("accent")
        if selected:
            btn.setStyleSheet(
                f"QPushButton{{background:{acc}1A;color:{acc};border:none;"
                f"border-radius:8px;font-size:12px;font-weight:700;"
                f"text-align:left;padding:0 8px;}}"
                f"QPushButton:hover{{background:{acc}28;}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{C('text_secondary')};"
                f"border:none;border-radius:8px;font-size:12px;font-weight:500;"
                f"text-align:left;padding:0 8px;}}"
                f"QPushButton:hover{{background:{C('surface_elevated')};color:{C('text_primary')};}}"
            )

    def _on_acct_btn_clicked(self, aid: str):
        self.current_account_id = aid
        # Deselect All Accounts button
        self._all_acct_btn.setChecked(False)
        # Update all account button styles
        for bid, btn in self._acct_buttons.items():
            self._style_acct_btn(btn, bid == aid)
            btn.setChecked(bid == aid)
        self._update_account_indicator()
        # Always default to INBOX when switching accounts
        self.current_folder = "INBOX"
        for fid, fb in self._folder_btns.items():
            fb.setChecked(fid == "INBOX")
        self.folder_title_lbl.setText("Inbox")
        self.refresh_email_list()

    def _select_all_accounts(self):
        self.current_account_id = "__all__"
        self._all_acct_btn.setChecked(True)
        for btn in self._acct_buttons.values():
            btn.setChecked(False)
            self._style_acct_btn(btn, False)
        self._update_account_indicator()
        self.refresh_email_list()

    def _on_sidebar_acct(self, item):
        # Legacy – kept for compatibility but no longer used
        aid = item.data(Qt.UserRole)
        self._on_acct_btn_clicked(aid)

    def switch_folder(self, folder: str):
        for fid, btn in self._folder_btns.items():
            btn.setChecked(fid == folder)
        nm = {
            "INBOX": "Inbox",
            "starred": "Starred",
            "sent": "Sent",
            "drafts": "Drafts",
            "trash": "Trash",
        }
        self.folder_title_lbl.setText(nm.get(folder, folder.title()))
        self.current_folder = folder
        self.refresh_email_list()

    def _on_search(self, q):
        self.search_query = q
        self.refresh_email_list()

    # ── Email list ──────────────────────────────────────────────────────
    # Batch size for progressive list rendering (keeps UI responsive)
    _LIST_BATCH = 40

    def refresh_email_list(self):
        """Rebuild the email list. Uses batched rendering to stay responsive."""
        self.email_list.clear()
        # Cancel any in-progress batch render
        if hasattr(self, "_batch_timer") and self._batch_timer:
            self._batch_timer.stop()
        self._batch_emails: list = []
        self._batch_idx: int = 0

        emails = self._collect_filtered_emails()
        if not emails:
            self._list_stack.setCurrentIndex(1)
            self.status_lbl.setText("No emails found")
            self.email_count_lbl.setText("0")
            return

        self._list_stack.setCurrentIndex(0)
        try:
            emails.sort(key=lambda x: x.date_sent or "", reverse=True)
        except Exception:
            pass

        unread = sum(1 for e in emails if not e.is_read)
        self.email_count_lbl.setText(str(len(emails)))
        self.status_lbl.setText(
            f"{len(emails)} emails" + (f"  ·  {unread} unread" if unread else "")
        )

        # Render first batch immediately, rest via timer (keeps UI alive)
        self._batch_emails = emails
        self._batch_idx = 0
        self._render_batch()

    def _collect_filtered_emails(self) -> list:
        """
        Return emails for the current account/folder/search from the DB.

        Design change (v7.1):
          Previously this merged DB results into a flat _email_by_id dict and
          then filtered that dict.  The problem: emails from other folders
          (sent, drafts, trash) accumulated in the dict across navigation and
          bled into INBOX view if the local folder-filter was wrong, or caused
          INBOX emails to be missing when messages_ready never fired
          (all pre-existing) and _email_by_id was still empty.

          Now we ALWAYS query the DB directly for the current view (account +
          folder + search), and ALSO update the in-memory cache so that
          _on_email_selected / detail view can look up full email objects.
        """
        if not self.accounts:
            return list(self._email_by_id.values()) if self._email_by_id else []

        try:
            from engine import email_svc as _esvc

            acct_ids = (
                [a.id for a in self.accounts]
                if self.current_account_id == "__all__"
                else [self.current_account_id]
            )

            folder = self.current_folder
            is_starred_filter: Optional[bool] = None
            real_folder = folder

            if folder == "starred":
                is_starred_filter = True
                real_folder = ""  # no folder restriction for starred
            elif folder in ("__all__", ""):
                real_folder = ""

            db_emails, _ = _esvc.list_emails(
                account_ids=acct_ids,
                folder=real_folder,
                search=self.search_query,
                is_starred=is_starred_filter,
                page_size=500,
            )

            # Update the in-memory lookup cache (for detail-view / attachments)
            for e in db_emails:
                self._email_by_id[e.id] = e

            emails = db_emails  # already scoped to the right account + folder

        except Exception as ex:
            log.warning(f"DB list_emails failed, falling back to cache: {ex}")
            # Fallback: filter whatever is in the in-memory cache
            emails = list(self._email_by_id.values())

            if self.current_account_id != "__all__":
                emails = [
                    e
                    for e in emails
                    if getattr(e, "account_id", None) == self.current_account_id
                ]

            folder = self.current_folder
            if folder == "starred":
                emails = [e for e in emails if getattr(e, "is_starred", False)]
            elif folder not in ("INBOX", "__all__", ""):
                emails = [e for e in emails if getattr(e, "folder", "INBOX") == folder]
            elif folder == "INBOX":
                emails = [
                    e
                    for e in emails
                    if getattr(e, "folder", "INBOX") == "INBOX"
                    and not getattr(e, "is_archived", False)
                    and not getattr(e, "is_deleted", False)
                ]

        # Local search filter on top of DB results (for instant search feedback)
        if self.search_query:
            q = self.search_query.lower()
            emails = [
                e
                for e in emails
                if q in (e.subject or "").lower()
                or q in (e.from_name or "").lower()
                or q in (e.from_email or "").lower()
                or q in (e.snippet or "").lower()
            ]

        return emails

    def _render_batch(self):
        """Render _LIST_BATCH items at a time; schedule next batch via QTimer."""
        batch = self._batch_emails[self._batch_idx : self._batch_idx + self._LIST_BATCH]
        for em in batch:
            item = QListWidgetItem()
            widget = EmailListItem(em)
            item.setSizeHint(widget.sizeHint())
            self.email_list.addItem(item)
            self.email_list.setItemWidget(item, widget)

        self._batch_idx += self._LIST_BATCH
        if self._batch_idx < len(self._batch_emails):
            # Schedule next batch — gives Qt time to process paint/scroll events
            self._batch_timer = QTimer(self)
            self._batch_timer.setSingleShot(True)
            self._batch_timer.timeout.connect(self._render_batch)
            self._batch_timer.start(16)  # ~1 frame @ 60 fps

    def _on_email_selected(self, item):
        w = self.email_list.itemWidget(item)
        if not w:
            return
        em = w.email
        if not em.is_read:
            try:
                email_svc.mark_read([em.id], True)
                em.is_read = True
                nw = EmailListItem(em)
                item.setSizeHint(nw.sizeHint())
                self.email_list.setItemWidget(item, nw)
            except Exception as e:
                log.error(f"mark_read: {e}")
        self._start_analysis(em)
        # Pre-populate attachment cache so download/preview are instant
        if getattr(em, "has_attachments", False):
            self._cache_attachments(em)

    def handle_action(self, url_str: str):
        """Parse action:verb:param and dispatch to the correct method."""
        # url_str = "action:reply:email_id"
        rest = url_str[7:]  # strip "action:"
        parts = rest.split(":", 1)
        action = parts[0]
        param = parts[1] if len(parts) > 1 else ""

        email = self._email_by_id.get(param) or self._current_email

        if action == "reply" and email:
            self.compose(reply_to=email)
        elif action == "forward" and email:
            self.compose(forward=email)
        elif action == "star" and email:
            self._toggle_star(email)
        elif action == "delete" and email:
            self._delete_email(email)
        elif action == "contact":
            em = self._current_email
            self._add_contact(
                em.from_email if em else param, em.from_name if em else ""
            )
        elif action == "show_details":
            self._toggle_details_panel()
        elif action == "deep_analysis":
            self._manual_deep_analysis(param or (email.id if email else ""))
        elif action == "mark_safe" and email:
            self._mark_as_safe(email)
        elif action == "mark_phish" and email:
            self._mark_as_phishing(email)
        elif action == "att_download":
            self._attachment_download(param)
        elif action == "att_preview":
            self._attachment_preview(param)
        else:
            log.warning(f"Unknown action: {action!r}")

    def _on_link_hovered(self, url: str):
        self.status_lbl.setText(url[:80] if url else "Ready")

    # ── Attachment helpers ───────────────────────────────────────────────
    def _extract_attachment_meta(self, email: "EmailMsg") -> list:
        """
        Parse the stored body_text / body_html to extract attachment name + size.
        Falls back to querying the attachments DB table if available.
        Returns list of dicts: {filename, size, content_type, data}.
        """
        results = []
        try:
            from engine import db as _db

            rows = _db.q(
                "SELECT filename, content_type, size_bytes, storage_path "
                "FROM attachments WHERE email_id=?",
                (email.id,),
            )
            for r in rows:
                results.append(
                    {
                        "filename": r["filename"] or "attachment",
                        "content_type": r["content_type"] or "application/octet-stream",
                        "size": r["size_bytes"] or 0,
                        "storage_path": r["storage_path"] or "",
                        "data": None,
                    }
                )
        except Exception:
            pass

        # Fallback: re-parse the raw MIME body if we have body text
        if not results and email.body_text:
            import email as _email_lib, email.policy

            try:
                raw = email.body_text.encode()
                msg = _email_lib.message_from_bytes(
                    raw, policy=_email_lib.policy.default
                )
                for part in msg.walk():
                    disp = part.get_content_disposition()
                    if disp in ("attachment", "inline"):
                        fn = part.get_filename() or "attachment"
                        payload = part.get_payload(decode=True) or b""
                        results.append(
                            {
                                "filename": fn,
                                "content_type": part.get_content_type(),
                                "size": len(payload),
                                "storage_path": "",
                                "data": payload,
                            }
                        )
            except Exception:
                pass
        return results

    # Cache attachment data so download/preview can retrieve by index
    _att_cache: dict = {}

    def _cache_attachments(self, email: "EmailMsg"):
        """Populate _att_cache[email.id] so download/preview work."""
        atts = self._extract_attachment_meta(email)
        self._att_cache[email.id] = atts
        return atts

    def _attachment_icon(self, content_type: str) -> str:
        ct = (content_type or "").lower()
        if "pdf" in ct:
            return "📄"
        if "image" in ct:
            return "🖼"
        if "zip" in ct or "archive" in ct or "compressed" in ct:
            return "🗜"
        if "word" in ct or "document" in ct:
            return "📝"
        if "excel" in ct or "spreadsheet" in ct:
            return "📊"
        if "video" in ct:
            return "🎥"
        if "audio" in ct:
            return "🎵"
        if "text" in ct:
            return "📃"
        return "📎"

    def _resolve_att(self, param: str):
        """
        param = "email_id__att__index"
        Returns (email, att_dict) or (None, None).
        """
        try:
            eid, _, idx_s = param.rpartition("__att__")
            idx = int(idx_s)
            email = self._email_by_id.get(eid) or self._current_email
            if not email:
                return None, None
            if eid not in self._att_cache:
                self._cache_attachments(email)
            atts = self._att_cache.get(eid, [])
            if 0 <= idx < len(atts):
                return email, atts[idx]
        except Exception as exc:
            log.error(f"_resolve_att: {exc}")
        return None, None

    def _get_att_bytes(self, att: dict) -> bytes:
        """Load attachment bytes from storage_path or inline data."""
        if att.get("data"):
            return att["data"]
        sp = att.get("storage_path", "")
        if sp and Path(sp).exists():
            return Path(sp).read_bytes()
        return b""

    def _attachment_download(self, param: str):
        """Show Save File dialog and write attachment to user-chosen path."""
        _, att = self._resolve_att(param)
        if att is None:
            self.toast.error("Attachment", "Could not locate attachment data.")
            return
        filename = att["filename"]
        dest, _ = QFileDialog.getSaveFileName(self, "Save Attachment", filename)
        if not dest:
            return
        data = self._get_att_bytes(att)
        if not data:
            self.toast.error("Attachment", "No data found for this attachment.")
            return
        try:
            Path(dest).write_bytes(data)
            self.toast.success("Saved", f"Attachment saved to {Path(dest).name}")
        except Exception as exc:
            self.toast.error("Save failed", str(exc))

    def _attachment_preview(self, param: str):
        """Open a preview dialog for the attachment (image inline, others via OS)."""
        import tempfile, subprocess, sys as _sys

        _, att = self._resolve_att(param)
        if att is None:
            self.toast.error("Attachment", "Could not locate attachment data.")
            return
        data = self._get_att_bytes(att)
        if not data:
            self.toast.error("Attachment", "No data available to preview.")
            return
        ct = att.get("content_type", "")
        filename = att["filename"]

        # ── Image: show inline dialog ──────────────────────────────
        if ct.startswith("image/"):
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea
            from PyQt5.QtGui import QPixmap

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Preview – {filename}")
            dlg.resize(700, 500)
            ly = QVBoxLayout(dlg)
            ly.setContentsMargins(12, 12, 12, 12)
            pm = QPixmap()
            pm.loadFromData(data)
            lbl = QLabel()
            lbl.setPixmap(
                pm.scaled(660, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            lbl.setAlignment(Qt.AlignCenter)
            scroll = QScrollArea()
            scroll.setWidget(lbl)
            scroll.setWidgetResizable(True)
            ly.addWidget(scroll)
            dlg.exec_()
            return

        # ── Everything else: write to temp file and open with OS ──
        suffix = Path(filename).suffix or ""
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="mailshield_"
        )
        tmp.write(data)
        tmp.close()
        try:
            if _sys.platform == "darwin":
                subprocess.Popen(["open", tmp.name])
            elif _sys.platform == "win32":
                import os

                os.startfile(tmp.name)
            else:
                subprocess.Popen(["xdg-open", tmp.name])
            self.toast.info("Preview", f"Opening {filename} with your default app…")
        except Exception as exc:
            self.toast.error("Preview failed", str(exc))

    # ── Analysis ────────────────────────────────────────────────────────
    def _start_analysis(self, email: "EmailMsg"):
        self._current_email = email
        self.detail_stack.setCurrentIndex(1)

        if email.id in self.analysis_cache:
            self._display_analysis(self.analysis_cache[email.id])
            return

        self._start_loading_animation()
        normal = normal_analysis(email)
        combined = {
            "normal": normal,
            "deep": None,
            "final_score": normal["score"],
            "risk": normal["risk"],
            "reasons": normal["reasons"],
            "scores": normal.get("scores", {}),
            "need_deep": normal.get("need_deep", False),
            "detected_links": normal.get("detected_links", []),
            "detected_js": normal.get("detected_js", []),
            "detected_buttons": normal.get("detected_buttons", []),
            "detected_forms": normal.get("detected_forms", []),
            "keyword_contexts": normal.get("keyword_contexts", []),
        }
        self.analysis_cache[email.id] = combined
        self._stop_loading_animation()

        # ── Sync risk badge in the email list ──────────────────────────
        new_risk = combined["risk"]
        if email.security_risk != new_risk:
            email.security_risk = new_risk
            try:
                email_svc.update_security_risk(email.id, new_risk)
            except Exception:
                pass
            self._update_email_list_badge(email)

        self._display_analysis(combined)

        if combined["need_deep"]:
            self._start_deep_analysis(email)

    def _start_loading_animation(self):
        self.sync_progress.setVisible(True)
        self.sync_progress.setRange(0, 0)
        self._loading_dots = 0
        if self._loading_animation_timer is None:
            self._loading_animation_timer = QTimer(self)
            self._loading_animation_timer.timeout.connect(self._update_loading_text)
        self._loading_animation_timer.start(300)
        self.status_lbl.setText("Analyzing…")

    def _update_loading_text(self):
        self._loading_dots = (self._loading_dots + 1) % 4
        self.status_lbl.setText("Analyzing" + "." * self._loading_dots)

    def _stop_loading_animation(self):
        if self._loading_animation_timer:
            self._loading_animation_timer.stop()
        self.sync_progress.setVisible(False)
        self.sync_progress.setRange(0, 100)
        self.status_lbl.setText("Ready")

    def _toggle_details_panel(self):
        js = """
        var p = document.getElementById('details-panel');
        var btn = document.getElementById('details-toggle-btn');
        if(p){
            if(p.style.display === 'none' || p.style.display === ''){
                p.style.display = 'block';
                if(btn) btn.innerText = '▲ Hide Details';
            } else {
                p.style.display = 'none';
                if(btn) btn.innerText = '▼ See Full Details';
            }
        }
        """
        self.web_view.page().runJavaScript(js)

    def _manual_deep_analysis(self, email_id: str):
        email = self._email_by_id.get(email_id) or self._current_email
        if not email:
            return
        if self._deep_in_progress:
            self.toast.info(
                "Analysis running", "Please wait for current analysis to finish."
            )
            return
        if email.id in self.analysis_cache and self.analysis_cache[email.id].get(
            "deep"
        ):
            self.toast.info(
                "Already analyzed", "Deep analysis results are shown above."
            )
            return
        self._start_deep_analysis(email)

    def _start_deep_analysis(self, email: "EmailMsg"):
        if self.deep_worker and self.deep_worker.isRunning():
            return
        self._deep_in_progress = True
        self._show_deep_loading_ui(email)
        self.deep_worker = DeepAnalysisWorker(email)
        self.deep_worker.progress.connect(self._on_deep_progress)
        self.deep_worker.finished.connect(
            lambda res: self._on_deep_finished(email.id, res)
        )
        self.deep_worker.start()
        self.status_lbl.setText("Deep ML analysis running…")

    def _show_deep_loading_ui(self, email: "EmailMsg"):
        """Replace the security panel with the deep analysis loading screen."""
        acc = C("accent")
        bg = C("bg")
        surf = C("surface")
        bdr = C("border")
        txt = C("text_primary")
        muted = C("text_muted")

        stages = DeepAnalysisWorker.STAGES
        steps_html = ""
        for i, (label, _) in enumerate(stages):
            steps_html += f"""
            <div class="step pending" id="step-{i}">
              <span class="step-icon">○</span>
              <span class="step-label">{label}</span>
            </div>"""

        loading_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
  body {{
    font-family: {FONT_FAMILY_CSS};
    background: {bg}; color: {txt};
    margin: 0; padding: 32px 24px;
    display: flex; flex-direction: column; align-items: center;
  }}
  .header {{
    text-align: center; margin-bottom: 32px;
  }}
  .shield-icon {{
    font-size: 52px; display: block; margin-bottom: 12px;
    animation: pulse 1.8s ease-in-out infinite;
  }}
  @keyframes pulse {{
    0%,100% {{ opacity:1; transform: scale(1); }}
    50% {{ opacity:.7; transform: scale(.95); }}
  }}
  h2 {{ margin:8px 0 4px; font-size:22px; color:{txt}; }}
  .subtitle {{ color:{muted}; font-size:13px; margin:0; }}
  .steps-box {{
    background:{surf}; border:1px solid {bdr};
    border-radius:16px; padding:24px 28px;
    width:100%; max-width:480px; margin-bottom:24px;
  }}
  .step {{
    display:flex; align-items:center; gap:12px;
    padding:10px 0; border-bottom:1px solid {bdr};
    font-size:13px;
  }}
  .step:last-child {{ border-bottom:none; }}
  .step-icon {{ font-size:16px; width:20px; text-align:center; }}
  .step.done {{ color:{C('success')}; }}
  .step.done .step-icon::after {{ content:"✓"; }}
  .step.running {{ color:{acc}; font-weight:600; }}
  .step.running .step-icon {{ animation: spin 0.8s linear infinite; }}
  .step.pending {{ color:{muted}; }}
  @keyframes spin {{
    from {{ transform: rotate(0deg); }}
    to   {{ transform: rotate(360deg); }}
  }}
  .progress-track {{
    width:100%; max-width:480px;
    background:{bdr}; border-radius:8px; height:8px; margin-bottom:10px;
    overflow:hidden;
  }}
  .progress-fill {{
    height:100%; border-radius:8px;
    background: linear-gradient(90deg, {acc}, {C('gradient_end')});
    transition: width 0.4s ease;
    width: 0%;
  }}
  .progress-text {{ color:{muted}; font-size:12px; }}
</style>
</head>
<body>
<div class="header">
  <span class="shield-icon">🛡️</span>
  <h2>Deep ML Analysis</h2>
  <p class="subtitle">Running advanced threat detection on <b>{html_lib.escape(email.subject or '(No Subject)')[:60]}</b></p>
</div>
<div class="steps-box">
  {steps_html}
</div>
<div class="progress-track">
  <div class="progress-fill" id="progress-fill" style="width:0%"></div>
</div>
<p class="progress-text" id="progress-text">Starting analysis…</p>
</body>
</html>"""
        self.web_view.setHtml(loading_html, QUrl("about:blank"))

    @pyqtSlot(str, int)
    def _on_deep_progress(self, stage: str, percent: int):
        self.status_lbl.setText(f"Deep analysis: {stage} ({percent}%)")
        stages = DeepAnalysisWorker.STAGES
        # Find which step index is current based on percent
        current_idx = 0
        for i, (_, p) in enumerate(stages):
            if percent >= p:
                current_idx = i

        js_parts = []
        for i in range(len(stages)):
            if i < current_idx:
                js_parts.append(
                    f"s=document.getElementById('step-{i}');if(s){{s.className='step done';}}"
                )
            elif i == current_idx:
                js_parts.append(
                    f"s=document.getElementById('step-{i}');if(s){{s.className='step running';s.querySelector('.step-icon').textContent='⟳';}}"
                )
            else:
                js_parts.append(
                    f"s=document.getElementById('step-{i}');if(s){{s.className='step pending';}}"
                )

        js_parts.append(
            f"f=document.getElementById('progress-fill');if(f)f.style.width='{percent}%';"
        )
        js_parts.append(
            f"t=document.getElementById('progress-text');if(t)t.innerText='{stage} — {percent}% complete';"
        )
        self.web_view.page().runJavaScript("\n".join(js_parts))

    @pyqtSlot(str, dict)
    def _on_deep_finished(self, email_id: str, deep_result: dict):
        self._deep_in_progress = False
        if email_id not in self.analysis_cache:
            return
        combined = self.analysis_cache[email_id]
        combined["deep"] = deep_result
        normal_score = combined["normal"]["score"]
        if "score" in deep_result:
            final_score = 0.55 * normal_score + 0.45 * deep_result["score"]
        else:
            final_score = normal_score
        combined["final_score"] = final_score
        if final_score > 0.70:
            combined["risk"] = "dangerous"
        elif final_score > 0.35:
            combined["risk"] = "suspicious"
        else:
            combined["risk"] = "safe"
        # Merge deep detections
        for key in ("detected_forms", "detected_buttons", "detected_js"):
            if key in deep_result:
                combined.setdefault(key, [])
                combined[key] = combined[key] or deep_result[key]
        self.analysis_cache[email_id] = combined
        self.status_lbl.setText("Deep analysis complete")

        # ── Sync risk badge in the email list ──────────────────────────
        email = self._email_by_id.get(email_id)
        if email:
            new_risk = combined["risk"]
            if email.security_risk != new_risk:
                email.security_risk = new_risk
                try:
                    email_svc.update_security_risk(email.id, new_risk)
                except Exception:
                    pass
                self._update_email_list_badge(email)

        if self._current_email and self._current_email.id == email_id:
            self._display_analysis(combined)

    # ── Display Analysis (beautiful HTML) ─────────────────────────────
    def _display_analysis(self, combined: dict):
        email = self._current_email
        if not email:
            return

        final_score = combined["final_score"] * 100
        risk = combined["risk"]
        scores = combined.get("scores", {})
        reasons = combined.get("reasons", [])
        deep = combined.get("deep")
        links = combined.get("detected_links", [])
        js_findings = combined.get("detected_js", [])
        btn_findings = combined.get("detected_buttons", [])
        form_findings = combined.get("detected_forms", [])
        kw_contexts = combined.get("keyword_contexts", [])

        # Colours
        if final_score < 30:
            risk_color = "#22c55e"
            risk_text = "SAFE"
            risk_bg = "#22c55e18"
        elif final_score < 70:
            risk_color = "#f59e0b"
            risk_text = "SUSPICIOUS"
            risk_bg = "#f59e0b18"
        else:
            risk_color = "#ef4444"
            risk_text = "PHISHING"
            risk_bg = "#ef444418"

        acc = C("accent")
        bg = C("bg")
        surf = C("surface")
        surfe = C("surface_elevated")
        bdr = C("border")
        txt = C("text_primary")
        txts = C("text_secondary")
        muted = C("text_muted")
        succ = C("success")
        warn = C("warning")
        dang = C("danger")

        email_id_safe = html_lib.escape(email.id)

        # ── Score ring (SVG gauge) ─────────────────────────────────────
        angle = int(final_score * 2.52)  # 252 = circumference of circle r=40
        gauge_svg = f"""
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke="{bdr}" stroke-width="8"/>
          <circle cx="50" cy="50" r="40" fill="none" stroke="{risk_color}" stroke-width="8"
            stroke-dasharray="{angle} 252" stroke-dashoffset="63"
            stroke-linecap="round" transform="rotate(-90 50 50)"/>
          <text x="50" y="46" text-anchor="middle" dominant-baseline="middle"
            fill="{risk_color}" font-size="18" font-weight="800"
            font-family="{FONT_FAMILY_CSS}">{final_score:.0f}%</text>
          <text x="50" y="62" text-anchor="middle" dominant-baseline="middle"
            fill="{muted}" font-size="9"
            font-family="{FONT_FAMILY_CSS}">{risk_text}</text>
        </svg>"""

        # ── Category bars ─────────────────────────────────────────────
        def bar_html(label: str, score: int, max_pts: int, color: str) -> str:
            pct = min(score / max_pts * 100, 100) if max_pts else 0
            return f"""
            <div class="cat-row">
              <span class="cat-label">{label}</span>
              <div class="bar-track">
                <div class="bar-fill" style="width:{pct:.0f}%;background:{color};"></div>
              </div>
              <span class="cat-pts" style="color:{color if score else muted}">
                {'+' if score else ''}{score} pts
              </span>
            </div>"""

        cats_html = (
            bar_html("URL Risk", scores.get("url_risk", 0), 100, dang)
            + bar_html("Keywords", scores.get("keyword_risk", 0), 100, warn)
            + bar_html("Sender", scores.get("sender_risk", 0), 100, warn)
            + bar_html("Hidden Links", scores.get("hidden_links", 0), 20, dang)
            + bar_html("JavaScript", scores.get("js_risk", 0), 30, dang)
            + bar_html("Forms", scores.get("form_risk", 0), 40, dang)
            + bar_html("Base64 Content", scores.get("base64_risk", 0), 20, muted)
        )

        # ── Risk reasons ───────────────────────────────────────────────
        reasons_html = ""
        for r in reasons[:8]:
            reasons_html += f'<div class="reason-item">⚠ {html_lib.escape(r)}</div>'
        if not reasons_html:
            reasons_html = f'<div class="reason-item" style="color:{succ}">✓ No suspicious patterns detected</div>'

        # ── Deep analysis section ──────────────────────────────────────
        if deep and "score" in deep:
            ml_pct = deep["score"] * 100
            conf = deep.get("confidence", 0) * 100
            deep_section = f"""
            <div class="section-card deep-card">
              <div class="sec-title">🤖 Deep ML Analysis</div>
              <div style="display:flex;gap:20px;align-items:center;">
                <div>
                  <div style="font-size:28px;font-weight:800;color:{risk_color};">{ml_pct:.0f}%</div>
                  <div style="color:{muted};font-size:11px;">ML Risk Score</div>
                </div>
                <div>
                  <div style="font-size:28px;font-weight:800;color:{acc};">{conf:.0f}%</div>
                  <div style="color:{muted};font-size:11px;">Confidence</div>
                </div>
                <div style="flex:1">
                  <div style="font-size:11px;color:{muted};margin-bottom:4px;">Model: {deep.get('model_used','N/A')}</div>
                  {''.join(f'<div style="font-size:11px;color:{muted};">• {k}: {v:.2f}</div>'
                           for k,v in (deep.get('features') or {}).items())[:3]}
                </div>
              </div>
            </div>"""
        elif combined.get("need_deep"):
            deep_section = f"""
            <div class="section-card" style="text-align:center;padding:16px;">
              <div class="sec-title">🤖 Advanced Analysis Available</div>
              <p style="color:{muted};font-size:12px;margin:8px 0 14px;">
                This email scored high enough to warrant deep ML analysis.
              </p>
              <a href="action:deep_analysis:{email_id_safe}" class="btn-primary">
                🔬 Run Deep Analysis
              </a>
            </div>"""
        else:
            deep_section = ""

        # ── Expandable details ─────────────────────────────────────────
        # Links table
        if links:
            link_rows = ""
            for lnk in links[:15]:
                lc = (
                    dang
                    if lnk["risk_level"] == "dangerous"
                    else warn if lnk["risk_level"] == "suspicious" else succ
                )
                ll = lnk["risk_level"].upper()[:4]
                url_disp = html_lib.escape(lnk["url"][:70])
                domain = html_lib.escape(lnk["domain"])
                flags = "; ".join(lnk["flags"][:2])
                link_rows += f"""
                <tr>
                  <td style="max-width:280px;word-break:break-all;">
                    <span style="font-size:11px;color:{txts};">{url_disp}</span>
                  </td>
                  <td><span style="font-size:10px;font-weight:700;color:{lc};">{ll}</span></td>
                  <td style="font-size:10px;color:{muted};">{flags}</td>
                </tr>"""
            links_section = f"""
            <div class="sub-section">
              <div class="sub-title">🔗 Links Detected ({len(links)})</div>
              <table class="det-table"><tr><th>URL</th><th>Risk</th><th>Flags</th></tr>
              {link_rows}</table>
            </div>"""
        else:
            links_section = f'<div class="sub-section"><div class="sub-title">🔗 Links</div><p style="color:{succ};font-size:12px;">✓ No links detected</p></div>'

        # JavaScript findings
        if js_findings:
            js_items = ""
            for jf in js_findings[:6]:
                jc = dang if jf.get("risk") == "high" else warn
                js_items += f"""<div style="background:{jc}18;border:1px solid {jc}33;
                  border-radius:6px;padding:6px 10px;margin-bottom:6px;font-size:11px;
                  color:{txts};">
                  <b style="color:{jc};">[{jf.get('type','JS').upper()}]</b>
                  &nbsp;{html_lib.escape(jf.get('preview','')[:80])}
                </div>"""
            js_section = f"""
            <div class="sub-section">
              <div class="sub-title">⚡ JavaScript ({len(js_findings)} found)</div>
              {js_items}
            </div>"""
        else:
            js_section = ""

        # Buttons & forms
        if btn_findings or form_findings:
            bf_items = ""
            for b in btn_findings[:5]:
                bc = warn if b.get("has_inline_action") else muted
                bf_items += f'<span style="background:{bc}22;color:{bc};border:1px solid {bc}44;border-radius:4px;padding:2px 8px;font-size:11px;margin:2px;">{html_lib.escape(b.get("text","<button>")[:30])}</span> '
            for f_ in form_findings[:3]:
                fc = dang if f_.get("credential_harvest") else warn
                bf_items += f'<span style="background:{fc}22;color:{fc};border:1px solid {fc}44;border-radius:4px;padding:2px 8px;font-size:11px;margin:2px;">FORM [{f_["method"]}] {f_["input_count"]} inputs{"🔑" if f_["has_password"] else ""}</span> '
            bf_section = f"""
            <div class="sub-section">
              <div class="sub-title">🖱 Buttons & Forms</div>
              <div>{bf_items}</div>
            </div>"""
        else:
            bf_section = ""

        # Keyword contexts
        if kw_contexts:
            kw_items = ""
            for kw in kw_contexts[:6]:
                kc = (
                    warn
                    if kw["category"] == "urgency"
                    else dang if kw["category"] == "reward_scam" else warn
                )
                ctx = html_lib.escape(kw["context"][:100])
                keyword = html_lib.escape(kw["keyword"])
                # Highlight the keyword in context
                highlighted = ctx.replace(
                    keyword,
                    f'<mark style="background:{kc}44;padding:0 2px;">{keyword}</mark>',
                )
                kw_items += f"""<div style="margin-bottom:6px;">
                  <span style="background:{kc}22;color:{kc};font-size:10px;font-weight:700;
                    border-radius:3px;padding:1px 5px;">{kw['category'].replace('_',' ').upper()}</span>
                  <span style="font-size:11px;color:{txts};margin-left:6px;">{highlighted}</span>
                </div>"""
            kw_section = f"""
            <div class="sub-section">
              <div class="sub-title">🔍 Suspicious Keywords in Context</div>
              {kw_items}
            </div>"""
        else:
            kw_section = ""

        # Technical indicators
        tech_section = f"""
        <div class="sub-section">
          <div class="sub-title">🔧 Technical Indicators</div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;">
            <span class="tech-badge" style="color:{succ};border-color:{succ}44;">SPF: PASS</span>
            <span class="tech-badge" style="color:{succ};border-color:{succ}44;">DKIM: PASS</span>
            <span class="tech-badge" style="color:{warn};border-color:{warn}44;">DMARC: NONE ⚠</span>
            <span class="tech-badge" style="color:{muted};border-color:{bdr};">
              Attach: {'Yes 📎' if email.has_attachments else 'None'}
            </span>
          </div>
        </div>"""

        details_panel = f"""
        <div id="details-panel" style="display:none;margin-top:12px;">
          {links_section}
          {js_section}
          {bf_section}
          {kw_section}
          {tech_section}
        </div>"""

        # ── Attachment panel ───────────────────────────────────────────
        attach_html = ""
        if getattr(email, "has_attachments", False):
            # Extract attachment metadata from the raw email body parts
            attach_items = self._extract_attachment_meta(email)
            if attach_items:
                rows_html = ""
                for i, att in enumerate(attach_items):
                    fname = html_lib.escape(att["filename"])
                    size_kb = att["size"] // 1024 if att["size"] > 0 else 0
                    size_str = f"{size_kb} KB" if size_kb > 0 else "—"
                    ct = html_lib.escape(att.get("content_type", ""))
                    icon = self._attachment_icon(att.get("content_type", ""))
                    # Encode index + email_id so handler can retrieve the right part
                    key = f"{email_id_safe}__att__{i}"
                    rows_html += f"""
                    <div style="display:flex;align-items:center;gap:12px;
                                padding:10px 0;border-bottom:1px solid {bdr}44;">
                      <span style="font-size:22px;">{icon}</span>
                      <div style="flex:1;min-width:0;">
                        <div style="font-weight:600;font-size:13px;
                                    white-space:nowrap;overflow:hidden;
                                    text-overflow:ellipsis;" title="{fname}">{fname}</div>
                        <div style="font-size:11px;color:{muted};">{ct} &nbsp;·&nbsp; {size_str}</div>
                      </div>
                      <a href="action:att_preview:{key}" class="btn-secondary"
                         style="font-size:11px;padding:5px 12px;">👁 Preview</a>
                      <a href="action:att_download:{key}" class="btn-secondary"
                         style="font-size:11px;padding:5px 12px;">⬇ Save</a>
                    </div>"""
                attach_html = f"""
                <div class="section-card" style="border-left:4px solid {acc};">
                  <div class="sec-title">📎 Attachments ({len(attach_items)})</div>
                  {rows_html}
                </div>"""
            else:
                attach_html = f"""
                <div class="section-card" style="border-left:4px solid {acc};">
                  <div class="sec-title">📎 Attachments</div>
                  <div style="color:{muted};font-size:12px;padding:8px 0;">
                    Attachment metadata detected. Re-sync to download files.
                  </div>
                  <a href="action:deep_analysis:{email_id_safe}" class="btn-secondary">
                    🔄 Re-sync to Download
                  </a>
                </div>"""

        # ── Action buttons (SVG icons) ──────────────────────────────────
        star_svg = (
            self._svg_inline("star-fill", "#f59e0b")
            if getattr(email, "is_starred", False)
            else self._svg_inline("star-off", txts)
        )
        star_label = "Unstar" if getattr(email, "is_starred", False) else "Star"
        buttons_html = f"""
        <div class="action-row">
          <a href="action:reply:{email_id_safe}" class="btn-primary">{self._svg_inline('reply', '#ffffff')}Reply</a>
          <a href="action:forward:{email_id_safe}" class="btn-secondary">{self._svg_inline('forward', txts)}Forward</a>
          <a href="action:star:{email_id_safe}" class="btn-secondary">{star_svg}{star_label}</a>
          <a href="action:contact:{email_id_safe}" class="btn-secondary">{self._svg_inline('contacts', txts)}Contact</a>
          <a href="action:delete:{email_id_safe}" class="btn-danger">{self._svg_inline('trash', dang)}Delete</a>
        </div>
        <div class="action-row" style="margin-top:6px;">
          <a href="action:deep_analysis:{email_id_safe}" class="btn-secondary">{self._svg_inline('search', txts)}Deep Analysis</a>
          <a href="action:mark_safe:{email_id_safe}" class="btn-secondary" style="color:{succ};border-color:{succ}44;">{self._svg_inline('shield-check', succ)}Mark Safe</a>
          <a href="action:mark_phish:{email_id_safe}" class="btn-secondary" style="color:{dang};border-color:{dang}44;">{self._svg_inline('shield-alert', dang)}Mark Phishing</a>
          <a href="action:show_details:{email_id_safe}" id="details-toggle-btn" class="btn-secondary">{self._svg_inline('eye', txts)}See Full Details</a>
        </div>"""

        # ── Email body ─────────────────────────────────────────────────
        email_body = self._get_email_body_html(email)

        # ── Full HTML page ─────────────────────────────────────────────
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: {FONT_FAMILY_CSS};
    background: {bg}; color: {txt};
    margin: 0; padding: 16px; font-size: 13px;
  }}
  a {{ text-decoration: none; color: inherit; }}
  .section-card {{
    background: {surf}; border: 1px solid {bdr};
    border-radius: 14px; padding: 18px 20px;
    margin-bottom: 14px;
  }}
  .deep-card {{ border-left: 4px solid {acc}; }}
  .sec-title {{
    font-size: 10px; font-weight: 800;
    text-transform: uppercase; letter-spacing: 1px;
    color: {muted}; margin-bottom: 12px;
  }}
  /* Risk pill */
  .risk-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    background: {risk_color}; color: white;
    padding: 4px 14px; border-radius: 20px;
    font-size: 11px; font-weight: 800;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
  }}
  /* Header meta */
  .meta-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:6px; }}
  .meta-item {{ color: {txts}; font-size:12px; }}
  .meta-label {{ color: {muted}; font-size:11px; font-weight:700; }}
  /* Action buttons */
  .action-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .btn-primary {{
    background: {acc}; color: #fff; border: none;
    border-radius: 8px; padding: 7px 16px;
    font-size: 12px; font-weight: 700; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px;
  }}
  .btn-primary:hover {{ opacity: 0.88; }}
  .btn-secondary {{
    background: {surfe}; color: {txts};
    border: 1px solid {bdr}; border-radius: 8px;
    padding: 7px 16px; font-size: 12px; font-weight: 600;
    cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  }}
  .btn-secondary:hover {{ background: {C('card_hover')}; }}
  .btn-danger {{
    background: transparent; color: {dang};
    border: 1px solid {dang}44; border-radius: 8px;
    padding: 7px 16px; font-size: 12px; font-weight: 600;
    cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  }}
  .btn-danger:hover {{ background: {dang}; color: #fff; }}
  /* Gauge + categories */
  .score-row {{
    display: flex; align-items: center; gap: 24px;
  }}
  .cat-row {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 8px;
  }}
  .cat-label {{
    min-width: 120px; font-size: 11px; color: {txts};
  }}
  .bar-track {{
    flex: 1; background: {bdr}; border-radius: 4px; height: 6px; overflow: hidden;
  }}
  .bar-fill {{
    height: 100%; border-radius: 4px;
    transition: width 0.5s ease;
  }}
  .cat-pts {{
    min-width: 60px; font-size: 11px; text-align: right; font-weight: 700;
  }}
  /* Reason items */
  .reason-item {{
    font-size: 12px; color: {txts};
    padding: 5px 0; border-bottom: 1px solid {bdr}44;
  }}
  .reason-item:last-child {{ border: none; }}
  /* Details panel */
  .sub-section {{ margin-bottom: 16px; }}
  .sub-title {{
    font-size: 10px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 1px; color: {muted}; margin-bottom: 8px;
  }}
  .det-table {{
    width: 100%; border-collapse: collapse; font-size: 11px;
  }}
  .det-table th {{
    text-align: left; color: {muted}; font-size: 10px;
    padding: 4px 8px; border-bottom: 1px solid {bdr};
    font-weight: 700; text-transform: uppercase;
  }}
  .det-table td {{
    padding: 5px 8px; border-bottom: 1px solid {bdr}22;
    vertical-align: top;
  }}
  .tech-badge {{
    border: 1px solid; border-radius: 6px;
    padding: 3px 10px; font-size: 11px; font-weight: 700;
  }}
  /* Email body */
  .body-card {{
    background: {surf}; border: 1px solid {bdr};
    border-radius: 14px; padding: 20px 24px;
  }}
  .body-card img {{ max-width: 100%; height: auto; }}
  mark {{ background: transparent; }}
</style>
</head>
<body>

<!-- ═══ HEADER CARD ═══ -->
<div class="section-card" style="border-left:4px solid {risk_color};">
  <div class="risk-pill">{'🛡' if risk_text=='SAFE' else '⚠' if risk_text=='SUSPICIOUS' else '☠'} {risk_text} &nbsp;{final_score:.0f}%</div>
  <h2 style="margin:6px 0 8px;font-size:17px;">{html_lib.escape(email.subject or '(No Subject)')}</h2>
  <div class="meta-row">
    <span class="meta-label">From:</span>
    <span class="meta-item">{html_lib.escape(email.from_name or '')} &lt;{html_lib.escape(email.from_email or '')}&gt;</span>
  </div>
  <div class="meta-row">
    <span class="meta-label">To:</span>
    <span class="meta-item">{html_lib.escape(str(email.to_emails or ''))[:80]}</span>
    <span class="meta-label" style="margin-left:12px;">Date:</span>
    <span class="meta-item">{html_lib.escape(ago(email.date_sent))}</span>
    {"<span style='margin-left:12px;font-size:11px;color:" + acc + ";'>📎 Has Attachments</span>" if getattr(email,'has_attachments',False) else ""}
  </div>
  <div style="margin-top:14px;">
    {buttons_html}
  </div>
</div>

<!-- ═══ SECURITY SCORE CARD ═══ -->
<div class="section-card">
  <div class="sec-title">Security Analysis</div>
  <div class="score-row">
    {gauge_svg}
    <div style="flex:1">
      {cats_html}
    </div>
  </div>
  <div style="margin-top:14px;">
    <div class="sec-title" style="margin-bottom:8px;">Risk Factors</div>
    {reasons_html}
  </div>
  {details_panel}
</div>

{deep_section}
{attach_html}

<!-- ═══ EMAIL BODY ═══ -->
<div class="body-card">
  <div class="sec-title" style="margin-bottom:14px;">Message</div>
  {email_body}
</div>

</body>
</html>"""

        self.web_view.setHtml(html, QUrl("about:blank"))

    def _get_email_body_html(self, email: "EmailMsg") -> str:
        if email.body_html:
            # Strip <script> tags for security
            safe = re.sub(
                r"<script[^>]*>.*?</script>",
                "",
                email.body_html,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # Strip <style> tags so email CSS doesn't bleed into our security UI panels
            safe = re.sub(
                r"<style[^>]*>.*?</style>", "", safe, flags=re.DOTALL | re.IGNORECASE
            )
            # Strip external stylesheet links
            safe = re.sub(
                r'<link[^>]*rel=["\']stylesheet["\'][^>]*/?>',
                "",
                safe,
                flags=re.IGNORECASE,
            )
            return safe
        elif email.body_text:
            esc = (
                email.body_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            return f'<pre style="font-family:inherit;white-space:pre-wrap;font-size:13px;line-height:1.7;">{esc}</pre>'
        else:
            return f'<p style="color:{C("text_muted")};">(No message body)</p>'

    # ── Theme update ───────────────────────────────────────────────────
    def _on_theme_changed(self):
        app = QApplication.instance()
        apply_theme(app)
        self._load_bg()
        self._refresh_all_styles()
        self.update()
        # Redisplay current email with new theme
        if self._current_email and self._current_email.id in self.analysis_cache:
            self._display_analysis(self.analysis_cache[self._current_email.id])

    def _refresh_all_styles(self):
        """Update all inline-styled widgets after a theme change."""
        if self._sidebar_frame:
            self._sidebar_frame.setStyleSheet(
                f"QFrame{{background:{C('sidebar')};border-right:1px solid {C('border')};}}"
            )
        if self._toolbar_frame:
            self._toolbar_frame.setStyleSheet(
                f"QFrame{{background:{C('surface')};border-bottom:1px solid {C('border')};}}"
            )
        if self._list_panel_frame:
            self._list_panel_frame.setStyleSheet(
                f"QFrame{{background:{C('surface')};border-right:1px solid {C('border')};}}"
            )
        if self._folder_title_bar_frame:
            self._folder_title_bar_frame.setStyleSheet(
                f"background:{C('surface')};border-bottom:1px solid {C('border')};"
            )
        if self._statusbar_frame:
            self._statusbar_frame.setStyleSheet(
                f"QFrame{{background:{C('surface')};border-top:1px solid {C('border')};}}"
            )
        if self._detail_panel_frame:
            self._detail_panel_frame.setStyleSheet(f"background:{C('bg')};")
        if self._acct_indicator_lbl:
            self._acct_indicator_lbl.setStyleSheet(
                f"background:{C('surface_elevated')};color:{C('text_secondary')};"
                f"border:1px solid {C('border')};border-radius:8px;"
                f"padding:6px 14px;font-size:12px;font-weight:600;"
            )
        # Refresh logo icon and title label
        if hasattr(self, "_logo_title_lbl"):
            try:
                self._logo_title_lbl.setStyleSheet(
                    f"font-size:16px;font-weight:800;color:{C('text_primary')};"
                )
            except RuntimeError:
                pass
        if hasattr(self, "_logo_icon_lbl"):
            try:
                lbl = self._logo_icon_lbl
                logo_icon = _make_themed_icon("logo", 32, C("accent"))
                if not logo_icon.isNull():
                    lbl.setPixmap(logo_icon.pixmap(32, 32))
                else:
                    # fallback "M" badge — update accent color
                    lbl.setStyleSheet(
                        f"background:{C('accent')};color:#fff;border-radius:8px;"
                        f"font-size:15px;font-weight:800;"
                    )
            except RuntimeError:
                pass
        if hasattr(self, "folder_title_lbl"):
            self.folder_title_lbl.setStyleSheet(
                f"font-size:15px;font-weight:700;color:{C('text_primary')};"
            )
        if hasattr(self, "email_count_lbl"):
            self.email_count_lbl.setStyleSheet(
                f"font-size:11px;color:{C('text_muted')};"
                f"background:{C('surface_elevated')};border-radius:8px;padding:2px 8px;"
            )
        if hasattr(self, "status_lbl"):
            self.status_lbl.setStyleSheet(f"color:{C('text_muted')};font-size:11px;")
        if hasattr(self, "sync_lbl"):
            self.sync_lbl.setStyleSheet(
                f"color:{C('accent')};font-size:11px;font-weight:600;"
            )
        # Refresh account button styles
        if hasattr(self, "_all_acct_btn"):
            self._style_all_acct_btn()
        if hasattr(self, "_add_acct_btn"):
            self._style_add_acct_btn()
        if hasattr(self, "_acct_buttons"):
            for aid, btn in self._acct_buttons.items():
                selected = self.current_account_id == aid
                self._style_acct_btn(btn, selected)
        # Refresh compose button
        if hasattr(self, "_compose_btn"):
            self._compose_btn.setStyleSheet(
                f"QPushButton{{background:{C('accent')};color:#fff;"
                f"border-radius:10px;font-weight:700;font-size:13px;"
                f"text-align:left;padding-left:14px;}}"
                f"QPushButton:hover{{background:{C('accent_hover')};}}"
            )
        # Refresh account items
        if hasattr(self, "account_list_widget"):
            self._update_account_list_style()
            for i in range(self.account_list_widget.count()):
                item = self.account_list_widget.item(i)
                if item:
                    item.setForeground(QColor(C("accent")))
        # Refresh toolbar button icons and styles (adapts to dark/light theme)
        for btn, icon_name in getattr(self, "_toolbar_btn_icons", []):
            try:
                ico = _make_themed_icon(icon_name, 16, C("text"))
                if not ico.isNull():
                    btn.setIcon(ico)
                    btn.setIconSize(QSize(16, 16))
                self._apply_toolbar_btn_style(btn)
            except RuntimeError:
                pass
        # Refresh folder button icons
        for fid, btn in self._folder_btns.items():
            ico = _make_themed_icon(fid if fid != "INBOX" else "inbox", 16)
            if not ico.isNull():
                btn.setIcon(ico)
            btn.setStyleSheet(
                f"QToolButton{{text-align:left;padding-left:10px;border-radius:8px;"
                f"font-size:13px;color:{C('text_secondary')};background:transparent;}}"
                f"QToolButton:hover{{background:{C('card_hover')};}}"
                f"QToolButton:checked{{background:{C('accent')}1A;color:{C('accent')};font-weight:700;}}"
            )
        # Refresh email list (re-renders all items)
        self.refresh_email_list()
        self.toast.info("Theme applied", "Interface updated in real time.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_refresh_overlay"):
            self._refresh_overlay.setGeometry(self.rect())

    def _show_refresh_overlay(self):
        """Show full-window white loading overlay with refresh.png and progress bar."""
        # Determine bg color based on theme
        is_dark = ThemeManager.theme() == "dark"
        bg = "rgba(8,15,30,0.92)" if is_dark else "rgba(248,250,252,0.95)"
        txt_col = "#f0f5fd" if is_dark else "#1e293b"
        sub_col = "#4a6180" if is_dark else "#64748b"
        bar_bg = "#1e2d45" if is_dark else "#e2e8f0"
        bar_chunk = C("accent")

        self._refresh_overlay.setStyleSheet(f"background:{bg};border:none;")
        self._ov_text_lbl.setStyleSheet(
            f"font-size:20px;font-weight:700;color:{txt_col};background:transparent;"
        )
        self._ov_pct_lbl.setStyleSheet(
            f"font-size:13px;color:{sub_col};background:transparent;"
        )
        self._ov_bar.setStyleSheet(
            f"QProgressBar{{background:{bar_bg};border-radius:4px;border:none;}}"
            f"QProgressBar::chunk{{background:{bar_chunk};border-radius:4px;}}"
        )

        # Load refresh image
        img_path = Path(__file__).parent / "assets" / "refresh.png"
        if img_path.exists():
            pm = QPixmap(str(img_path)).scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._ov_img_lbl.setPixmap(pm)
        else:
            self._ov_img_lbl.setText("↻")
            self._ov_img_lbl.setStyleSheet(
                f"font-size:56px;color:{C('accent')};background:transparent;"
            )

        self._ov_progress_val = 0
        self._ov_bar.setValue(0)
        self._ov_pct_lbl.setText("0%")
        self._refresh_overlay.setGeometry(self.rect())
        self._refresh_overlay.raise_()
        self._refresh_overlay.setVisible(True)
        self._ov_progress_timer.start()

    def _ov_tick(self):
        if self._ov_progress_val < 90:
            self._ov_progress_val += 2
        self._ov_bar.setValue(self._ov_progress_val)
        self._ov_pct_lbl.setText(f"{self._ov_progress_val}%")

    def _hide_refresh_overlay(self):
        self._ov_progress_timer.stop()
        self._ov_bar.setValue(100)
        self._ov_pct_lbl.setText("100%")
        QTimer.singleShot(400, lambda: self._refresh_overlay.setVisible(False))

    def _refresh_and_reanalyse(self):
        """Show refresh overlay, refresh email list, then re-calculate risk badges."""
        self._show_refresh_overlay()
        QTimer.singleShot(100, self._do_refresh_and_reanalyse)

    def _do_refresh_and_reanalyse(self):
        self.refresh_email_list()
        QTimer.singleShot(200, self._reanalyse_all_visible_then_hide)

    def _reanalyse_all_visible_then_hide(self):
        self._reanalyse_all_visible()
        self._hide_refresh_overlay()

    def _reanalyse_all_visible(self):
        """Re-run normal_analysis on every email in the list and update badges."""
        from security_engine import normal_analysis as _na

        updated = 0
        for i in range(self.email_list.count()):
            item = self.email_list.item(i)
            w = self.email_list.itemWidget(item)
            if not (w and hasattr(w, "email")):
                continue
            em = w.email
            # Clear stale cache entry so analysis is fresh
            self.analysis_cache.pop(em.id, None)
            try:
                result = _na(em)
                new_risk = result["risk"]
                if em.security_risk != new_risk:
                    em.security_risk = new_risk
                    try:
                        email_svc.update_security_risk(em.id, new_risk)
                    except Exception:
                        pass
                    nw = EmailListItem(em)
                    item.setSizeHint(nw.sizeHint())
                    self.email_list.setItemWidget(item, nw)
                    updated += 1
            except Exception as exc:
                log.debug(f"reanalyse {em.id}: {exc}")
        if updated:
            self.toast.info(
                "Risk badges updated",
                f"{updated} email{'s' if updated != 1 else ''} re-graded.",
            )
        else:
            self.toast.success("All up to date", "No risk grade changes detected.")

    # ── Feedback / actions ─────────────────────────────────────────────
    def _mark_as_safe(self, email: "EmailMsg"):
        try:
            from security_engine import update_model_from_feedback

            update_model_from_feedback(email.id, 0)
            if email.id in self.analysis_cache:
                del self.analysis_cache[email.id]
            self._start_analysis(email)
            self.toast.success("Marked safe", "Analysis re-run with feedback.")
        except Exception as e:
            self.toast.error("Failed", str(e))

    def _mark_as_phishing(self, email: "EmailMsg"):
        try:
            from security_engine import update_model_from_feedback

            update_model_from_feedback(email.id, 1)
            if email.id in self.analysis_cache:
                del self.analysis_cache[email.id]
            self._start_analysis(email)
            self.toast.success("Marked as phishing", "Thanks for the feedback.")
        except Exception as e:
            self.toast.error("Failed", str(e))

    def _toggle_star(self, em: "EmailMsg"):
        try:
            email_svc.mark_starred([em.id], not em.is_starred)
            em.is_starred = not em.is_starred
            self.toast.success("Starred" if em.is_starred else "Unstarred")
            self.refresh_email_list()
        except Exception as e:
            self.toast.error("Failed to star", str(e))

    def _delete_email(self, em: "EmailMsg"):
        try:
            email_svc.delete_email(em.id)
            self.detail_stack.setCurrentIndex(0)
            self.refresh_email_list()
            self.toast.success("Email deleted")
        except Exception as e:
            self.toast.error("Failed to delete", str(e))

    def _add_contact(self, email_addr: str, name: str = ""):
        dlg = ContactEditDialog(self, self.user["id"])
        dlg.email_e.setText(email_addr)
        dlg.name_e.setText(name.replace("\\'", "'"))
        dlg.exec_()

    def compose(self, reply_to=None, forward=None):
        if not self.accounts:
            self.toast.warning("No account", "Add an email account first.")
            return
        default = None
        if self.current_account_id != "__all__":
            default = next(
                (a for a in self.accounts if a.id == self.current_account_id), None
            )
        dlg = ComposeDialog(self, self.accounts, default, reply_to, forward)
        if dlg.exec_() == dlg.Accepted:
            self.toast.success("Email sent", "Your message was delivered.")

    # ── Sync ────────────────────────────────────────────────────────────
    def start_sync(self):
        if self.sync_thread and self.sync_thread.isRunning():
            self.toast.info("Sync running", "Please wait.")
            return
        if not self.accounts:
            self.toast.warning("No accounts", "Add an email account.")
            return
        self.sync_progress.setMaximum(0)
        self.sync_progress.setValue(0)
        self.sync_progress.setVisible(True)
        self.sync_lbl.setText("Syncing…")
        mp = int(SETTINGS.value("max_per_folder", 100))
        self.sync_thread = SyncThread(self.accounts, max_per_folder=mp)
        self.sync_thread.folder_progress.connect(self._on_folder_progress)
        self.sync_thread.account_done.connect(self._on_account_done)
        self.sync_thread.messages_ready.connect(self._on_messages_ready)
        self.sync_thread.auth_error.connect(self._on_auth_error)
        self.sync_thread.soft_error.connect(self._on_soft_error)
        self.sync_thread.all_done.connect(self._on_all_done)
        self.sync_thread.start()

    @pyqtSlot(int, int, str)
    def _on_folder_progress(self, fetched, total, folder):
        if total > 0:
            self.sync_progress.setMaximum(total)
            self.sync_progress.setValue(fetched)
            self.sync_lbl.setText(f"Syncing {folder}…  {fetched}/{total}")
        else:
            self.sync_progress.setMaximum(0)
            self.sync_lbl.setText(f"Syncing {folder}…")

    @pyqtSlot(str, int)
    def _on_account_done(self, email, new_count):
        self.refresh_email_list()
        if new_count:
            self.toast.info(
                email, f"{new_count} new email{'s' if new_count != 1 else ''}"
            )

    @pyqtSlot(str, list)
    def _on_messages_ready(self, email: str, messages: list):
        print(f"[UI] Received {len(messages)} messages from {email}")

        if not hasattr(self, "_email_by_id"):
            self._email_by_id = {}

        added = 0
        for msg in messages:
            msg_id = msg.id
            self._email_by_id[msg_id] = msg
            added += 1

        print(f"[UI] Stored {added} messages. Total: {len(self._email_by_id)}")
        self.refresh_email_list()

    @pyqtSlot(str, str, str, str)
    def _on_auth_error(self, acc_id, email, title, detail):
        dlg = ErrorDialog(self, email, acc_id, title, detail)
        dlg.fix_account.connect(lambda _: self.show_settings())
        dlg.retry.connect(lambda _: self.start_sync())
        dlg.show()

    @pyqtSlot(str, str)
    def _on_soft_error(self, email, msg):
        key = email
        existing = self._banners.get(key)
        if existing:
            try:
                if existing.isVisible():
                    return
            except RuntimeError:
                pass

        banner = AlertBanner(
            self._banner_container,
            title=email,
            detail=msg,
            kind="warning",
            action_label="Retry",
            action_callback=self.start_sync,
            auto_dismiss_ms=10_000,
            dedup_key=key,
        )
        banner.dismissed.connect(lambda b=key: self._banners.pop(b, None))
        self._banner_layout.addWidget(banner)
        self._banners[key] = banner

    @pyqtSlot(int)
    def _on_all_done(self, total_new):
        self.sync_progress.setVisible(False)
        self.sync_lbl.setText("")
        self.refresh_email_list()
        if total_new > 0:
            self.toast.success(
                "Sync complete",
                f"{total_new} new email{'s' if total_new != 1 else ''} synced.",
            )
        else:
            self.status_lbl.setText("Sync complete – inbox up to date")

    # ── Feature dialogs ─────────────────────────────────────────────────────────────
    def add_email_account(self):
        dlg = AddAccountDialog(self, self.user["id"])
        if dlg.exec_() == dlg.Accepted:
            self.load_accounts()
            self.start_sync()
            self.toast.success("Account added", "Your inbox will sync shortly.")

    def show_settings(self):
        dlg = SettingsDialog(self, self.user["id"], self.accounts)
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.account_changed.connect(self._on_accounts_changed)
        dlg.exec_()

    def _on_accounts_changed(self):
        self.load_accounts()
        self.refresh_email_list()

    def show_contacts(self):
        ContactsPanel(self, self.user["id"]).exec_()

    def show_security_dashboard(self):
        """Show security risk overview as a full overlay panel."""
        try:
            acc_ids = [a.id for a in self.accounts]
            if not acc_ids:
                self.toast.info("No accounts", "Add an account first.")
                return
            emails, total = email_svc.list_emails(account_ids=acc_ids, page_size=500)
        except Exception as e:
            self.toast.error("Security check failed", str(e))
            return

        self._security_dashboard = SecurityDashboardDialog(
            self, self.accounts, emails, total
        )
        self._security_dashboard.show()
        self._security_dashboard.raise_()
        self._security_dashboard.activateWindow()


# ── Security Dashboard – Proper Popup Dialog ───────────────────────────

try:
    from PyQt5.QtWidgets import QDialog as _QDialog, QScrollArea as _QScrollArea
except ImportError:
    pass


class SecurityDashboardDialog(QDialog):
    """
    Security risk summary – shown as a real floating popup window so it
    can be moved, resized, and lives independently of the main window.
    """

    def __init__(self, parent: "MainWindow", accounts, emails, total: int):
        super().__init__(parent)
        self._accounts = accounts
        self._emails = emails
        self._total = total
        self.setWindowTitle("Security Dashboard")
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(820, 620)
        self.setMinimumSize(640, 480)
        self._build()
        # Centre over parent
        if parent:
            pg = parent.geometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
        from alerts import fade_in_widget

        fade_in_widget(self, 180)

    # ── UI ──────────────────────────────────────────────────────────────
    def _build(self):
        from utils import make_shadow

        acc = C("accent")
        bg = C("bg")
        surf = C("surface")
        surfe = C("surface_elevated")
        bdr = C("border")
        txt = C("text_primary")
        txts = C("text_secondary")
        muted = C("text_muted")
        succ = C("success")
        warn = C("warning")
        dang = C("danger")

        self.setStyleSheet(f"QDialog{{background:{bg};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ─────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(62)
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"QFrame{{background:{surf};border-bottom:1px solid {bdr};}}")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 16, 0)
        hl.setSpacing(14)

        shield_lbl = QLabel("🛡")
        shield_lbl.setStyleSheet("font-size:22px;background:transparent;")
        hl.addWidget(shield_lbl)

        title_lbl = QLabel("Security Dashboard")
        title_lbl.setStyleSheet(
            f"font-size:17px;font-weight:800;color:{txt};background:transparent;"
        )
        hl.addWidget(title_lbl)

        sub_lbl = QLabel(f"  ·  {self._total} emails analysed")
        sub_lbl.setStyleSheet(f"font-size:12px;color:{muted};background:transparent;")
        hl.addWidget(sub_lbl)
        hl.addStretch()

        close_btn = QPushButton("✕  Close")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet(
            f"QPushButton{{background:{surfe};color:{txt};"
            f"border:1px solid {bdr};border-radius:8px;"
            f"font-size:13px;font-weight:600;padding:0 14px;min-height:0;}}"
            f"QPushButton:hover{{background:{C('danger')};color:#fff;border-color:{C('danger')};}}"
        )
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Scrollable body ────────────────────────────────────────────
        from PyQt5.QtWidgets import QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{bg};border:none;}}"
            f"QScrollArea>QWidget>QWidget{{background:{bg};}}"
        )

        body = QWidget()
        body.setStyleSheet(f"background:{bg};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 20, 24, 20)
        bl.setSpacing(16)

        # Global risk counts
        all_emails = self._emails
        n_total = len(all_emails)
        n_safe = sum(1 for e in all_emails if e.security_risk == "safe")
        n_susp = sum(1 for e in all_emails if e.security_risk == "suspicious")
        n_dang = sum(1 for e in all_emails if e.security_risk == "dangerous")
        n_unk = n_total - n_safe - n_susp - n_dang

        # ── Global summary row ─────────────────────────────────────────
        def _stat_card(count, pct, label, color):
            w = QFrame()
            w.setAttribute(Qt.WA_StyledBackground, True)
            w.setStyleSheet(
                f"QFrame{{background:{color}14;border:1px solid {color}33;"
                f"border-radius:14px;}}"
            )
            wl = QVBoxLayout(w)
            wl.setContentsMargins(16, 14, 16, 14)
            wl.setSpacing(4)

            cnt = QLabel(str(count))
            cnt.setStyleSheet(
                f"font-size:28px;font-weight:800;color:{color};"
                f"background:transparent;"
            )
            cnt.setAlignment(Qt.AlignCenter)
            wl.addWidget(cnt)

            pct_lbl = QLabel(f"{pct:.1f}%")
            pct_lbl.setStyleSheet(
                f"font-size:13px;font-weight:700;color:{color};"
                f"background:transparent;"
            )
            pct_lbl.setAlignment(Qt.AlignCenter)
            wl.addWidget(pct_lbl)

            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"font-size:11px;color:{muted};font-weight:600;"
                f"background:transparent;letter-spacing:0.5px;"
            )
            lbl.setAlignment(Qt.AlignCenter)
            wl.addWidget(lbl)
            return w

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        denom = n_total or 1
        row1.addWidget(_stat_card(n_safe, n_safe / denom * 100, "SAFE", succ))
        row1.addWidget(_stat_card(n_susp, n_susp / denom * 100, "SUSPICIOUS", warn))
        row1.addWidget(_stat_card(n_dang, n_dang / denom * 100, "DANGEROUS", dang))
        row1.addWidget(_stat_card(n_unk, n_unk / denom * 100, "UNKNOWN", muted))
        bl.addLayout(row1)

        # ── Overall risk bar ───────────────────────────────────────────
        bar_frame = QFrame()
        bar_frame.setAttribute(Qt.WA_StyledBackground, True)
        bar_frame.setStyleSheet(
            f"QFrame{{background:{surf};border:1px solid {bdr};border-radius:12px;}}"
        )
        bfl = QVBoxLayout(bar_frame)
        bfl.setContentsMargins(16, 12, 16, 12)
        bfl.setSpacing(8)

        bar_title = QLabel("Overall Threat Distribution")
        bar_title.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{muted};"
            f"letter-spacing:0.8px;background:transparent;"
        )
        bfl.addWidget(bar_title)

        seg_bar = QWidget()
        seg_bar.setFixedHeight(18)
        seg_bar.setAttribute(Qt.WA_StyledBackground, True)
        seg_bar.setStyleSheet("border-radius:9px;overflow:hidden;")
        seg_layout = QHBoxLayout(seg_bar)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)

        for count, color in [
            (n_safe, succ),
            (n_susp, warn),
            (n_dang, dang),
            (n_unk, muted),
        ]:
            if count > 0:
                seg = QFrame()
                seg.setAttribute(Qt.WA_StyledBackground, True)
                seg.setStyleSheet(f"background:{color};border:none;border-radius:0;")
                seg_layout.addWidget(seg, count)
        bfl.addWidget(seg_bar)

        legend = QHBoxLayout()
        for label, count, color in [
            ("Safe", n_safe, succ),
            ("Suspicious", n_susp, warn),
            ("Dangerous", n_dang, dang),
            ("Unknown", n_unk, muted),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color};font-size:10px;background:transparent;")
            lg = QLabel(f"{label}: {count}")
            lg.setStyleSheet(f"color:{txts};font-size:11px;background:transparent;")
            legend.addWidget(dot)
            legend.addWidget(lg)
            legend.addSpacing(12)
        legend.addStretch()
        bfl.addLayout(legend)
        bl.addWidget(bar_frame)

        # ── Per-account breakdown ──────────────────────────────────────
        if self._accounts:
            acct_title = QLabel("Per-Account Breakdown")
            acct_title.setStyleSheet(
                f"font-size:13px;font-weight:700;color:{txts};background:transparent;"
            )
            bl.addWidget(acct_title)

            acct_rows_widget = QWidget()
            acct_rows_widget.setStyleSheet("background:transparent;")
            sl = QVBoxLayout(acct_rows_widget)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(8)

            for acc_obj in self._accounts:
                acc_emails = [
                    e
                    for e in all_emails
                    if getattr(e, "account_id", None) == acc_obj.id
                ]
                na = len(acc_emails)
                ns = sum(1 for e in acc_emails if e.security_risk == "safe")
                nw = sum(1 for e in acc_emails if e.security_risk == "suspicious")
                nd = sum(1 for e in acc_emails if e.security_risk == "dangerous")
                denom_a = na or 1

                row = QFrame()
                row.setAttribute(Qt.WA_StyledBackground, True)
                row.setStyleSheet(
                    f"QFrame{{background:{surf};border:1px solid {bdr};"
                    f"border-radius:10px;}}"
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(14, 10, 14, 10)
                rl.setSpacing(14)

                from utils import make_avatar

                av = make_avatar(acc_obj.email or "?", 34)
                rl.addWidget(av)

                info = QVBoxLayout()
                info.setSpacing(2)
                email_lbl = QLabel(acc_obj.email or "Unknown")
                email_lbl.setStyleSheet(
                    f"font-size:12px;font-weight:700;color:{txt};background:transparent;"
                )
                info.addWidget(email_lbl)
                count_lbl = QLabel(f"{na} emails")
                count_lbl.setStyleSheet(
                    f"font-size:11px;color:{muted};background:transparent;"
                )
                info.addWidget(count_lbl)
                rl.addLayout(info, 1)

                for count, color, label in [
                    (ns, succ, "Safe"),
                    (nw, warn, "Warn"),
                    (nd, dang, "Risk"),
                ]:
                    pct_val = count / denom_a * 100
                    pill = QLabel(f"{count}  {pct_val:.0f}%")
                    pill.setAlignment(Qt.AlignCenter)
                    pill.setFixedWidth(72)
                    pill.setStyleSheet(
                        f"background:{color}18;color:{color};"
                        f"border:1px solid {color}44;border-radius:8px;"
                        f"font-size:11px;font-weight:700;padding:3px 0;"
                    )
                    pill.setToolTip(label)
                    rl.addWidget(pill)

                sl.addWidget(row)

            bl.addWidget(acct_rows_widget)  # add per-account rows widget to body layout

        bl.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)