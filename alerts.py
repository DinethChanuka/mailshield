"""
MailShield – Alert System v5.0
Level 1 – Toast      : top-right stack, 3 s auto-dismiss, smooth restack on close
Level 2 – Banner     : one-per-dedup_key strip, 3 s auto-dismiss
Level 3 – ErrorDialog: modal for auth failures with Fix / Retry
"""

from __future__ import annotations

import logging
from typing import List

from PyQt5.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    pyqtSignal,
)
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsOpacityEffect,
)
from PyQt5.QtGui import QColor

from theme import C
from utils import make_shadow

log = logging.getLogger("mailshield")

_MARGIN = 16
_W = 356
_GAP = 8


def _fade(widget, start, end, duration=200, on_done=None):
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    if on_done:
        anim.finished.connect(on_done)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def fade_in_widget(widget, duration=200):
    _fade(widget, 0.0, 1.0, duration)


# ─── Toast ─────────────────────────────────────────────────────────────
class Toast(QWidget):
    closed = pyqtSignal(object)

    _K = {
        "success": ("#22c55e", "✓"),
        "error": ("#ef4444", "✕"),
        "warning": ("#f59e0b", "⚠"),
        "info": ("#3b82f6", "i"),
    }

    def __init__(self, parent, title, message="", kind="info", ms=3000):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._ms = ms
        self._build(title, message, kind)

    def _build(self, title, message, kind):
        acc, sym = self._K.get(kind, self._K["info"])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 6, 0)

        card = QFrame()
        card.setFixedWidth(_W)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(
            f"QFrame{{"
            f"  background:{C('surface_elevated')};"
            f"  border-radius:14px;"
            f"  border:1px solid {C('border')};"
            f"  border-left:4px solid {acc};"
            f"}}"
        )
        card.setGraphicsEffect(make_shadow(28, 8, 80))
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 12, 12)
        cl.setSpacing(5)

        # Header row
        row = QHBoxLayout()
        row.setSpacing(10)

        ic = QLabel(sym)
        ic.setFixedSize(26, 26)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"background:{acc};color:#fff;border-radius:13px;"
            f"font-size:11px;font-weight:900;border:none;"
        )
        row.addWidget(ic)

        tl = QLabel(title)
        tl.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{C('text_primary')};background:transparent;"
        )
        row.addWidget(tl, 1)

        xb = QPushButton("×")
        xb.setFixedSize(22, 22)
        xb.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('text_muted')};"
            f"border:none;font-size:16px;padding:0;min-height:0;border-radius:11px;}}"
            f"QPushButton:hover{{color:{C('text_primary')};background:{C('surface')};}}"
        )
        xb.clicked.connect(self._dismiss)
        row.addWidget(xb)
        cl.addLayout(row)

        if message:
            ml = QLabel(message)
            ml.setWordWrap(True)
            ml.setStyleSheet(
                f"font-size:12px;color:{C('text_secondary')};padding-left:36px;"
                f"background:transparent;"
            )
            cl.addWidget(ml)

        # Auto-dismiss timer (no visible countdown bar)
        self._tick = QTimer(self)
        self._tick.setSingleShot(True)
        self._tick.timeout.connect(self._dismiss)
        self._tick.start(self._ms)
        fade_in_widget(self, 160)

    def _dismiss(self):
        self._tick.stop()
        _fade(self, 1.0, 0.0, 160, on_done=self._done)

    def _done(self):
        self.closed.emit(self)
        self.deleteLater()


class ToastManager(QWidget):
    """Stacks toasts top-right; restacks smoothly when one closes."""

    MAX = 5

    def __init__(self, parent):
        super().__init__(parent)
        self._q: List[Toast] = []

    # All kinds default to 3 s; errors stay 5 s so the user can read them
    def success(self, t, m=""):
        self._add(t, m, "success", 3000)

    def error(self, t, m=""):
        self._add(t, m, "error", 5000)

    def warning(self, t, m=""):
        self._add(t, m, "warning", 3000)

    def info(self, t, m=""):
        self._add(t, m, "info", 3000)

    def _add(self, title, msg, kind, ms):
        self._prune()
        if len(self._q) >= self.MAX:
            try:
                self._q[0]._dismiss()
            except RuntimeError:
                pass
            self._prune()
        t = Toast(self.parent(), title, msg, kind, ms)
        t.adjustSize()
        t.closed.connect(self._on_closed)
        self._q.append(t)
        self._restack()
        t.show()

    def _on_closed(self, t):
        try:
            self._q.remove(t)
        except ValueError:
            pass
        self._prune()
        self._restack(animate=True)

    def _prune(self):
        live = []
        for t in self._q:
            try:
                if t.isVisible():
                    live.append(t)
            except RuntimeError:
                pass
        self._q = live

    def _restack(self, animate=False):
        p = self.parent()
        if not p:
            return
        x = p.width() - _W - _MARGIN
        y = _MARGIN
        for t in self._q:
            try:
                if t.isVisible():
                    if animate:
                        a = QPropertyAnimation(t, b"pos", t)
                        a.setDuration(160)
                        a.setStartValue(t.pos())
                        a.setEndValue(QPoint(x, y))
                        a.setEasingCurve(QEasingCurve.OutCubic)
                        a.start(QPropertyAnimation.DeleteWhenStopped)
                    else:
                        t.move(x, y)
                    y += t.height() + _GAP
            except RuntimeError:
                pass


# ─── Alert Banner ──────────────────────────────────────────────────────
class AlertBanner(QFrame):
    dismissed = pyqtSignal()

    _C = {
        "warning": ("#f59e0b", "#f59e0b12"),
        "error": ("#ef4444", "#ef444412"),
        "info": ("#3b82f6", "#3b82f612"),
        "success": ("#22c55e", "#22c55e12"),
    }
    _ICON = {"warning": "⚠", "error": "✕", "info": "i", "success": "✓"}

    def __init__(
        self,
        parent,
        title,
        detail="",
        kind="warning",
        action_label="",
        action_callback=None,
        auto_dismiss_ms=3_000,  # ← 3 seconds default
        dedup_key="",
    ):
        super().__init__(parent)
        self.dedup_key = dedup_key
        fg, bg = self._C.get(kind, self._C["warning"])
        self.setStyleSheet(
            f"QFrame{{background:{bg};border-bottom:2px solid {fg}44;"
            f"border-top:1px solid {fg}22;}}"
        )
        self.setFixedHeight(46)
        self._build(fg, title, detail, action_label, action_callback, kind)
        fade_in_widget(self, 180)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._close)
        if auto_dismiss_ms > 0:
            self._timer.start(auto_dismiss_ms)

    def _build(self, fg, title, detail, action_label, action_callback, kind="warning"):
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 12, 0)
        row.setSpacing(8)

        sym = self._ICON.get(kind, "●")
        ic = QLabel(sym)
        ic.setFixedSize(20, 20)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"color:#fff;background:{fg};border-radius:10px;"
            f"font-size:10px;font-weight:900;border:none;"
        )
        row.addWidget(ic)

        lbl = QLabel(
            f"<b>{title}</b>"
            + (
                f"  <span style='font-weight:400;opacity:0.8'>{detail}</span>"
                if detail
                else ""
            )
        )
        lbl.setStyleSheet(
            f"color:{C('text_primary')};font-size:12px;background:transparent;"
        )
        row.addWidget(lbl, 1)

        if action_label and action_callback:
            ab = QPushButton(action_label)
            ab.setStyleSheet(
                f"QPushButton{{background:{fg};color:#fff;border:none;border-radius:6px;"
                f"padding:4px 14px;font-size:11px;font-weight:700;min-height:0;}}"
                f"QPushButton:hover{{background:{fg}cc;}}"
            )
            ab.clicked.connect(action_callback)
            row.addWidget(ab)

        xb = QPushButton("x")
        xb.setFixedSize(22, 22)
        xb.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('text_muted')};border:none;"
            f"font-size:14px;padding:0;min-height:0;border-radius:11px;}}"
            f"QPushButton:hover{{background:{fg}33;color:{fg};}}"
        )
        xb.clicked.connect(self._close)
        row.addWidget(xb)

    def _close(self):
        self._timer.stop()
        _fade(self, 1.0, 0.0, 140, on_done=self._done)

    def _done(self):
        self.dismissed.emit()
        self.hide()


# ─── Error Dialog ──────────────────────────────────────────────────────
class ErrorDialog(QWidget):
    fix_account = pyqtSignal(str)
    retry = pyqtSignal(str)

    def __init__(self, parent, account_email, account_id, title, detail):
        super().__init__(parent)
        self._id = account_id
        self.setWindowFlags(Qt.SubWindow)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget{{background:{C('surface_elevated')};border:1px solid {C('danger')}55;"
            f"border-radius:16px;}}"
        )
        self.setGraphicsEffect(make_shadow(48, 12, 130))
        self._build(account_email, title, detail)
        self.setFixedWidth(420)
        self.adjustSize()
        self._centre()
        fade_in_widget(self, 200)

    def _build(self, email, title, detail):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 24)
        lay.setSpacing(16)

        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        ic_wrap = QFrame()
        ic_wrap.setFixedSize(48, 48)
        ic_wrap.setStyleSheet(
            f"background:{C('danger')}18;border-radius:24px;border:none;"
        )
        ic_l = QVBoxLayout(ic_wrap)
        ic_l.setContentsMargins(0, 0, 0, 0)
        ic = QLabel("!")
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"color:{C('danger')};font-size:24px;font-weight:900;background:transparent;"
        )
        ic_l.addWidget(ic)
        hdr.addWidget(ic_wrap)

        info = QVBoxLayout()
        info.setSpacing(3)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            f"font-size:15px;font-weight:700;color:{C('text_primary')};background:transparent;"
        )
        info.addWidget(t_lbl)
        e_lbl = QLabel(email)
        e_lbl.setStyleSheet(
            f"font-size:12px;color:{C('text_muted')};background:transparent;"
        )
        info.addWidget(e_lbl)
        hdr.addLayout(info, 1)

        xb = QPushButton("x")
        xb.setFixedSize(28, 28)
        xb.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C('text_muted')};border:none;"
            f"font-size:16px;padding:0;min-height:0;border-radius:14px;}}"
            f"QPushButton:hover{{background:{C('surface')};color:{C('text_primary')};}}"
        )
        xb.clicked.connect(self._dismiss)
        hdr.addWidget(xb)
        lay.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C('border')};border:none;")
        lay.addWidget(sep)

        dl = QLabel(detail)
        dl.setWordWrap(True)
        dl.setStyleSheet(
            f"font-size:12px;color:{C('text_secondary')};line-height:1.6;background:transparent;"
        )
        lay.addWidget(dl)

        br = QHBoxLayout()
        br.setSpacing(10)

        rb = QPushButton("Retry")
        rb.setFixedHeight(40)
        rb.setStyleSheet(
            f"QPushButton{{background:{C('surface')};color:{C('text')};border:1px solid {C('border')};"
            f"border-radius:10px;font-weight:600;font-size:13px;min-height:0;}}"
            f"QPushButton:hover{{background:{C('card_hover')};border-color:{C('accent')}55;}}"
        )
        rb.clicked.connect(lambda: (self.retry.emit(self._id), self._dismiss()))
        br.addWidget(rb)

        fb = QPushButton("Fix Account Settings")
        fb.setFixedHeight(40)
        fb.setStyleSheet(
            f"QPushButton{{background:{C('danger')};color:#fff;border:none;border-radius:10px;"
            f"font-weight:600;font-size:13px;min-height:0;}}"
            f"QPushButton:hover{{background:{C('danger')}cc;}}"
        )
        fb.clicked.connect(lambda: (self.fix_account.emit(self._id), self._dismiss()))
        br.addWidget(fb)
        lay.addLayout(br)

    def _dismiss(self):
        _fade(self, 1.0, 0.0, 180, on_done=self.deleteLater)

    def _centre(self):
        p = self.parent()
        if p:
            self.move(
                (p.width() - self.width()) // 2, (p.height() - self.height()) // 2
            )
