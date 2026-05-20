"""
MailShield – Utility helpers
Pure functions – no painting, no side-effects.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QGraphicsDropShadowEffect

from theme import C

log = logging.getLogger("mailshield")


# ── Time formatting ────────────────────────────────────────────────────
def ago(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo:
            from datetime import timezone

            now = datetime.now(timezone.utc)
        else:
            now = datetime.now()
            dt = dt.replace(tzinfo=None)
        diff = (now - dt).total_seconds()
        if diff < 60:
            return "Just now"
        if diff < 3600:
            return f"{int(diff / 60)}m"
        if diff < 86400:
            return f"{int(diff / 3600)}h"
        if diff < 604800:
            return f"{int(diff / 86400)}d"
        return dt.strftime("%b %d")
    except Exception:
        return ""


# ── Avatar colour ──────────────────────────────────────────────────────
_AVATAR_PALETTE = [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#f43f5e",
    "#10b981",
    "#0ea5e9",
    "#84cc16",
]


def avatar_color(name: str) -> str:
    return _AVATAR_PALETTE[sum(ord(c) for c in (name or "?")) % len(_AVATAR_PALETTE)]


def make_avatar(name: str, size: int = 40) -> QLabel:
    """Return a square, round-cornered label showing the first letter."""
    lbl = QLabel((name or "?")[0].upper())
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignCenter)
    r = size // 2
    lbl.setStyleSheet(
        f"background: {avatar_color(name)}; color: #fff; "
        f"border-radius: {r}px; font-size: {size // 2 - 2}px; font-weight: 700;"
    )
    return lbl


# ── Section label ──────────────────────────────────────────────────────
def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {C('text_muted')}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px; padding: 4px 10px 2px 10px; background: transparent;"
    )
    return lbl


# ── Shadow effect factory ──────────────────────────────────────────────
def make_shadow(
    blur: int = 16, y_offset: int = 2, opacity: int = 80
) -> QGraphicsDropShadowEffect:
    """
    Always create a *new* QGraphicsDropShadowEffect.
    A single effect instance must NOT be shared between widgets;
    doing so triggers the QPainter::begin / setWorldTransform crash.
    """
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(blur)
    eff.setOffset(0, y_offset)
    eff.setColor(QColor(0, 0, 0, opacity))
    return eff


# ── IMAP / SMTP error mapping ──────────────────────────────────────────
def map_imap_error(raw: str) -> Tuple[str, str]:
    """
    Returns (short_title, user_friendly_detail) from a raw IMAP exception
    string so the UI can show something actionable instead of a stack trace.
    """
    e = str(raw).upper()

    if any(
        k in e
        for k in (
            "AUTHENTICATIONFAILED",
            "AUTHENTICATE",
            "LOGINFAILED",
            "INVALID CREDENTIALS",
            "BAD CREDENTIALS",
        )
    ):
        return (
            "Authentication failed",
            "The password was rejected. For Gmail/Yahoo/Outlook you must use "
            "an App Password, not your regular account password.",
        )
    if any(k in e for k in ("CERTIFICATE_VERIFY_FAILED", "SSL", "CERTIFICATE")):
        return (
            "SSL / certificate error",
            "Could not establish a secure connection. "
            "Check your network or the IMAP host setting.",
        )
    if any(k in e for k in ("TIMEOUT", "TIMED OUT", "TIMEDOUT")):
        return (
            "Connection timed out",
            "The mail server did not respond in time. "
            "Check your internet connection and try again.",
        )
    if any(k in e for k in ("ECONNREFUSED", "CONNECTION REFUSED", "REFUSED")):
        return (
            "Connection refused",
            "Could not reach the mail server. "
            "Verify the IMAP host and port in Account Settings.",
        )
    if "OVERQUOTA" in e or "QUOTA" in e:
        return (
            "Mailbox over quota",
            "Your mailbox is full. Free up space in your email provider.",
        )
    if any(k in e for k in ("READONLY", "READ-ONLY")):
        return (
            "Mailbox read-only",
            "This folder is currently read-only on the server.",
        )
    if any(k in e for k in ("NETWORK", "SOCKET", "IOERROR", "BROKEN PIPE")):
        return (
            "Network error",
            "The connection was interrupted. Check your internet connection.",
        )
    # generic fallback – still better than a raw Python exception
    short = str(raw)[:120]
    return ("Sync error", short)


def map_smtp_error(raw: str) -> Tuple[str, str]:
    e = str(raw).upper()
    if any(
        k in e for k in ("AUTHENTICATE", "AUTH", "LOGINFAILED", "535", "534", "530")
    ):
        return (
            "SMTP authentication failed",
            "Could not log in to the outgoing mail server. "
            "Check your App Password and SMTP settings.",
        )
    if any(k in e for k in ("RECIPIENT", "RCPT", "550", "551", "553")):
        return (
            "Invalid recipient",
            "The server rejected one or more recipient addresses. "
            "Check the To/CC fields.",
        )
    if "QUOTA" in e or "552" in e:
        return (
            "Mailbox full",
            "The recipient's mailbox is full. Try again later.",
        )
    if any(k in e for k in ("TIMEOUT", "TIMED OUT")):
        return (
            "SMTP timeout",
            "The outgoing server did not respond. Check your connection.",
        )
    short = str(raw)[:120]
    return ("Send failed", short)
