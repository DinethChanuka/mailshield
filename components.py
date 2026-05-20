"""
MailShield – Shared UI Components
CardWidget · PasswordField · EmailListItem (with attachment icon)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QSize, QByteArray
from PyQt5.QtGui import QColor, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QFrame,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QSizePolicy,
)

from theme import C, FONT_FAMILY_CSS
from utils import ago, make_avatar, avatar_color

if TYPE_CHECKING:
    try:
        from engine import EmailMsg
    except ImportError:
        pass

try:
    from engine import EmailMsg  # type: ignore[assignment]
except ImportError:
    EmailMsg = object  # type: ignore[assignment,misc]


# ── Attachment SVG ─────────────────────────────────────────────────────
_ATTACHMENT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
  fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66
           l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
</svg>"""


def _attachment_pixmap(size: int = 14, color: str = "#64748b") -> QPixmap:
    svg_data = _ATTACHMENT_SVG.format(color=color).encode()
    renderer = QSvgRenderer(QByteArray(svg_data))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


# ── Card ──────────────────────────────────────────────────────────────
class CardWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {C('surface')};
                border: 1px solid {C('border')};
                border-radius: 12px;
            }}
        """
        )


# ── PasswordField ──────────────────────────────────────────────────────
class PasswordField(QWidget):
    def __init__(self, placeholder: str = "Password", parent=None):
        super().__init__(parent)
        ly = QHBoxLayout(self)
        ly.setSpacing(0)
        ly.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setMinimumHeight(40)
        self.edit.setStyleSheet(
            f"""
            QLineEdit {{
                border-radius: 8px 0 0 8px;
                border: 1px solid {C('border')};
                border-right: none;
                background: {C('surface')};
                color: {C('text')};
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border-color: {C('accent')}; }}
        """
        )
        ly.addWidget(self.edit)

        self._eye = QPushButton("◉")
        self._eye.setFixedSize(40, 40)
        self._eye.setCheckable(True)
        self._eye.setStyleSheet(
            f"""
            QPushButton {{
                background: {C('surface')};
                border: 1px solid {C('border')};
                border-left: none;
                border-radius: 0 8px 8px 0;
                color: {C('text_muted')};
                font-size: 14px;
                padding: 0;
                min-height: 0;
            }}
            QPushButton:hover   {{ background: {C('surface_elevated')}; }}
            QPushButton:checked {{ color: {C('accent')}; }}
        """
        )
        self._eye.toggled.connect(
            lambda on: self.edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        ly.addWidget(self._eye)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, t: str):
        self.edit.setText(t)

    @property
    def returnPressed(self):
        return self.edit.returnPressed


# ── EmailListItem ──────────────────────────────────────────────────────
class EmailListItem(QWidget):
    """
    One row in the email list.
    Shows sender, subject, snippet, timestamp, risk badge, and attachment icon.
    """

    def __init__(self, email: "EmailMsg", parent=None):
        super().__init__(parent)
        self.email = email
        self._build()

    def _build(self):
        unread = not self.email.is_read
        risk = self.email.security_risk or "unknown"

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Unread stripe
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(
            f"background: {C('accent') if unread else 'transparent'}; border: none;"
        )
        root.addWidget(stripe)

        inner = QHBoxLayout()
        inner.setContentsMargins(12, 10, 14, 10)
        inner.setSpacing(12)

        # Avatar
        av = make_avatar(self.email.from_name or self.email.from_email or "?", 36)
        inner.addWidget(av)

        # Text column
        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.setContentsMargins(0, 0, 0, 0)

        # Row 1: sender + timestamp
        r1 = QHBoxLayout()
        r1.setSpacing(4)
        sender = QLabel(self.email.from_name or self.email.from_email or "Unknown")
        sender.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 13px; "
            f"font-weight: {'700' if unread else '500'};"
        )
        sender.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        r1.addWidget(sender)

        # Attachment icon (before timestamp)
        if getattr(self.email, "has_attachments", False):
            att_lbl = QLabel()
            att_lbl.setPixmap(_attachment_pixmap(12, C("text_muted")))
            att_lbl.setFixedSize(14, 14)
            att_lbl.setToolTip("Has attachments")
            r1.addWidget(att_lbl)

        ts = QLabel(ago(self.email.date_sent))
        ts.setStyleSheet(
            f"color: {C('accent') if unread else C('text_secondary')}; "
            f"font-size: 11px; font-weight: {'700' if unread else '500'};"
        )
        r1.addWidget(ts)
        txt.addLayout(r1)

        # Subject
        subj = QLabel(self.email.subject or "(No Subject)")
        subj.setStyleSheet(
            f"color: {C('text_primary') if unread else C('text_secondary')}; "
            f"font-size: 12px; font-weight: {'600' if unread else '400'};"
        )
        subj.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        txt.addWidget(subj)

        # Snippet
        snip = (self.email.snippet or "")[:88]
        if snip:
            sl = QLabel(snip)
            sl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
            sl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            txt.addWidget(sl)

        inner.addLayout(txt, 1)

        # Right: risk badge + unread dot
        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignTop | Qt.AlignRight)

        _risk = {
            "safe": (C("success"), "SAFE"),
            "suspicious": (C("warning"), "WARN"),
            "dangerous": (C("danger"), "RISK"),
            "unknown": (C("text_muted"), "?"),
        }
        rc, rl = _risk.get(risk, (C("text_muted"), "?"))
        badge = QLabel(rl)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(40)
        badge.setStyleSheet(
            f"background: {rc}; color: #fff; border-radius: 4px; "
            f"padding: 2px 0; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;"
        )
        right.addWidget(badge)

        if unread:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {C('accent')}; border-radius: 4px;")
            right.addWidget(dot, 0, Qt.AlignRight)

        inner.addLayout(right)

        wrap = QFrame()
        wrap.setLayout(inner)
        wrap.setStyleSheet("background: transparent; border: none;")
        root.addWidget(wrap, 1)

    def sizeHint(self):
        return QSize(300, 74)


# ── Empty state ────────────────────────────────────────────────────────
class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        ly = QVBoxLayout(self)
        ly.setAlignment(Qt.AlignCenter)
        ly.setSpacing(14)

        ic = QLabel(icon)
        ic.setFixedSize(72, 72)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"background: {C('surface_elevated')}; color: {C('text_muted')}; "
            f"border-radius: 36px; font-size: 30px;"
        )
        ly.addWidget(ic, 0, Qt.AlignHCenter)

        t = QLabel(title)
        t.setStyleSheet(f"color: {C('text_muted')}; font-size: 15px; font-weight: 600;")
        t.setAlignment(Qt.AlignCenter)
        ly.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
            s.setAlignment(Qt.AlignCenter)
            s.setWordWrap(True)
            ly.addWidget(s)
