"""
MailShield – Scoped QSS for the security dashboard & ML panel.
Isolated from email content styles to prevent bleeding.
"""

from theme import C


def analysis_panel_qss():
    """Return scoped style sheet for #SecurityPanel and #MLPanel."""
    return f"""
    QWidget#SecurityPanel {{
        background: rgba(15,20,38,0.85);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 16px;
    }}
    QWidget#SecurityPanel QLabel {{
        color: {C('text')};
        background: transparent;
    }}
    QWidget#SecurityPanel QProgressBar {{
        background: rgba(255,255,255,0.08);
        height: 6px;
        border-radius: 3px;
    }}
    QWidget#SecurityPanel QProgressBar::chunk {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {C('danger')},
            stop:1 {C('warning')}
        );
        border-radius: 3px;
    }}

    QWidget#MLPanel {{
        background: rgba(15,20,38,0.85);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 16px;
    }}
    QWidget#MLPanel QLabel {{
        color: {C('text')};
        background: transparent;
    }}
    QWidget#MLPanel QProgressBar {{
        background: rgba(255,255,255,0.08);
        height: 6px;
        border-radius: 3px;
    }}
    QWidget#MLPanel QProgressBar::chunk {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {C('danger')},
            stop:1 {C('warning')}
        );
        border-radius: 3px;
    }}
    """
