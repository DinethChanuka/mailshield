"""
MailShield – Background Workers
All IMAP / SMTP work runs here, never on the GUI thread.
Signals carry friendly, pre-mapped error strings (see utils.map_imap_error).
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

from engine import Account, IMAPSyncer
from utils import map_imap_error

log = logging.getLogger("mailshield")


class SyncThread(QThread):
    """
    Syncs one or more accounts sequentially.

    Signals
    -------
    folder_started(account_email, folder_name, estimated_total)
        Emitted at the beginning of each folder sync.
    folder_progress(fetched, total, folder_name)
        Emitted as messages arrive.  total may be 0 (unknown).
    account_done(account_email, new_count)
        Emitted after each account finishes successfully.
    auth_error(account_id, account_email, friendly_title, friendly_detail)
        Emitted for authentication failures – caller shows ErrorDialog.
    soft_error(account_email, friendly_message)
        Emitted for non-fatal per-folder errors (caller shows Banner/Toast).
    all_done(total_new)
        Emitted when every account has been processed.
    """

    folder_started = pyqtSignal(str, str, int)  # email, folder, est_total
    folder_progress = pyqtSignal(int, int, str)  # fetched, total, folder
    account_done = pyqtSignal(str, int)  # email, new_count
    messages_ready = pyqtSignal(str, list)  # email, List[EmailMsg]
    auth_error = pyqtSignal(str, str, str, str)  # id, email, title, detail
    soft_error = pyqtSignal(str, str)  # email, friendly_msg
    all_done = pyqtSignal(int)  # total_new

    def __init__(self, accounts: List[Account], max_per_folder: int = 100):
        super().__init__()
        self.accounts = accounts
        self.max_per_folder = max_per_folder

    def run(self):
        total_new = 0
        for acc in self.accounts:
            try:
                syncer = IMAPSyncer(acc)

                def _progress(fetched: int, total: int, folder: str, _acc=acc):
                    self.folder_progress.emit(fetched, total, folder)

                messages, new_count, errors = syncer.sync(
                    on_progress=_progress,
                    max_per_folder=self.max_per_folder,
                )
                total_new += new_count
                self.account_done.emit(acc.email, new_count)

                # ── Always push a fresh snapshot of this account's emails ──
                # When total_new == 0 (all emails pre-existed in DB, common on
                # subsequent launches), 'messages' is empty and the old
                # `if messages:` guard silently skipped the signal — leaving the
                # UI with a blank list for that account.  We now ALWAYS load the
                # current INBOX state from the DB and emit it so the UI cache
                # stays warm regardless of whether new mail arrived.
                try:
                    from engine import email_svc as _esvc

                    db_msgs, _ = _esvc.list_emails(
                        account_ids=[acc.id],
                        folder="INBOX",
                        page_size=500,
                    )
                    # Merge: new fetched emails take priority (they carry fresh
                    # security analysis), pre-existing DB records fill the rest.
                    merged: dict = {m.id: m for m in db_msgs}
                    for m in messages:
                        merged[m.id] = m  # new/re-fetched trumps DB row
                    if merged:
                        self.messages_ready.emit(acc.email, list(merged.values()))
                    elif messages:
                        self.messages_ready.emit(acc.email, messages)
                except Exception as _e:
                    log.warning(f"[SyncThread] post-sync DB load for {acc.email}: {_e}")
                    if messages:
                        self.messages_ready.emit(acc.email, messages)

                for raw_err in errors:
                    title, detail = map_imap_error(raw_err)
                    self.soft_error.emit(acc.email, f"{title}: {detail}")

            except Exception as exc:
                raw = str(exc)
                log.error(f"[SyncThread] {acc.email}: {raw}")
                title, detail = map_imap_error(raw)

                # Decide severity
                if any(
                    k in raw.upper()
                    for k in (
                        "AUTHENTICATIONFAILED",
                        "AUTHENTICATE",
                        "LOGINFAILED",
                        "INVALID CREDENTIALS",
                        "BAD CREDENTIALS",
                    )
                ):
                    self.auth_error.emit(acc.id, acc.email, title, detail)
                else:
                    self.soft_error.emit(acc.email, f"{title}: {detail}")

        self.all_done.emit(total_new)
