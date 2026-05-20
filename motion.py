"""
MailShield – Motion & Animation Helpers
Smooth, fast, Material‑3 style transitions.
"""

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve


def fade_in(widget, duration=180):
    """Fade in a QWidget using window opacity. Duration in ms."""
    widget.setWindowOpacity(0.0)
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)


def slide_up(widget, dy=14, duration=200):
    """Slide the widget up from below by dy pixels."""
    geo = widget.geometry()
    start = geo.adjusted(0, dy, 0, dy)
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setStartValue(start)
    anim.setEndValue(geo)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
