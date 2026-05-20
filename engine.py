"""
MailShield – Core Engine (Enhanced v2)
SQLite storage · IMAP sync · SMTP send · AES-256 encryption · ML security scoring
"""

from __future__ import annotations

import base64
import email as email_lib
import email.header
import email.utils
import hashlib
import imaplib
import json
import math
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import bcrypt
import certifi
import chardet
from bs4 import BeautifulSoup

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
except ImportError as e:
    raise ImportError("Missing 'pycryptodome'. pip install pycryptodome") from e

# Import the correct security engine (single source of truth)
from security_engine import normal_analysis

# ── Paths ──────────────────────────────────────────────────────────────
APP_DIR = Path.home() / ".mailshield"
DB_PATH = APP_DIR / "mailshield.db"
MODEL_DIR = APP_DIR / "models"
ATTACH_DIR = APP_DIR / "attachments"
BG_IMAGE_PATH = APP_DIR / "assets" / "bg.jpg"
for _d in (APP_DIR, MODEL_DIR, ATTACH_DIR, APP_DIR / "assets"):
    _d.mkdir(parents=True, exist_ok=True)


# ── Time helpers ───────────────────────────────────────────────────────
def utc_to_local(utc_dt_str: str) -> str:
    if not utc_dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().isoformat()
    except Exception:
        return ""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Password hashing ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))


# ── Encryption (AES-256-GCM) ───────────────────────────────────────────
class Encryptor:
    KEY_FILE = APP_DIR / ".key"

    def __init__(self):
        if self.KEY_FILE.exists():
            self._key = self.KEY_FILE.read_bytes()
        else:
            self._key = get_random_bytes(32)
            self.KEY_FILE.write_bytes(self._key)
            os.chmod(self.KEY_FILE, 0o600)

    def encrypt(self, text: str) -> str:
        iv = get_random_bytes(12)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=iv)
        ct, tag = cipher.encrypt_and_digest(text.encode())
        return base64.urlsafe_b64encode(iv + ct + tag).decode()

    def decrypt(self, data: str) -> str:
        raw = base64.urlsafe_b64decode(data)
        iv, ct, tag = raw[:12], raw[12:-16], raw[-16:]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ct, tag).decode()


_enc = Encryptor()
encrypt = _enc.encrypt
decrypt = _enc.decrypt


# ── Database ───────────────────────────────────────────────────────────
class Database:
    def __init__(self, path: Path = DB_PATH):
        self._path = str(path)
        self._local = threading.local()
        self._setup()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _setup(self):
        with sqlite3.connect(self._path) as c:
            c.executescript(
                """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    email TEXT, hashed_pw TEXT, display_name TEXT,
    theme TEXT DEFAULT 'dark', created_at TEXT, last_login TEXT
);
CREATE TABLE IF NOT EXISTS login_logs (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    login_time TEXT, ip TEXT DEFAULT 'local',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    provider TEXT NOT NULL, email TEXT NOT NULL,
    display_name TEXT, color TEXT DEFAULT '#4A9EFF',
    enc_access_token TEXT, enc_refresh_token TEXT,
    enc_password TEXT, imap_host TEXT, imap_port INTEGER DEFAULT 993,
    smtp_host TEXT, smtp_port INTEGER DEFAULT 587,
    use_ssl INTEGER DEFAULT 1, last_sync TEXT,
    last_uid INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
    notifications_enabled INTEGER DEFAULT 1,
    UNIQUE(user_id, email)
);
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
    message_id TEXT, thread_id TEXT, uid INTEGER,
    folder TEXT DEFAULT 'INBOX', category TEXT DEFAULT 'primary',
    from_email TEXT NOT NULL, from_name TEXT,
    to_emails TEXT, cc_emails TEXT,
    subject TEXT, snippet TEXT, body_text TEXT, body_html TEXT,
    date_sent TEXT, is_read INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0, is_draft INTEGER DEFAULT 0,
    is_sent INTEGER DEFAULT 0, has_attachments INTEGER DEFAULT 0,
    snoozed_until TEXT, tags TEXT DEFAULT '[]',
    security_risk TEXT DEFAULT 'unknown',
    security_score REAL DEFAULT 0, security_json TEXT,
    ml_priority REAL DEFAULT 0.5,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_emails_account  ON emails(account_id, folder, date_sent DESC);
CREATE INDEX IF NOT EXISTS ix_emails_thread   ON emails(thread_id);
CREATE INDEX IF NOT EXISTS ix_emails_security ON emails(security_risk);
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY, email_id TEXT NOT NULL,
    filename TEXT, content_type TEXT, size_bytes INTEGER,
    storage_path TEXT, is_inline INTEGER DEFAULT 0, file_hash TEXT,
    FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY, user_id TEXT, action TEXT,
    detail TEXT, ip TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS trusted_senders (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    pattern TEXT NOT NULL, is_domain INTEGER DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, pattern)
);
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    name TEXT, email TEXT, phone TEXT, company TEXT,
    notes TEXT, created_at TEXT, last_contact TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, email)
);
-- ML Feedback table (new)
CREATE TABLE IF NOT EXISTS ml_feedback (
    id TEXT PRIMARY KEY,
    email_id TEXT,
    label INTEGER,           -- 1 = phishing, 0 = safe, -1 = unknown
    features TEXT,           -- JSON
    created_at TEXT
);
-- ML model state persistence (new)
CREATE TABLE IF NOT EXISTS ml_model_state (
    id TEXT PRIMARY KEY,
    weights TEXT,            -- JSON of ML_WEIGHTS dict
    bias REAL,
    updated_at TEXT
);
"""
            )

    def run(self, sql: str, params=()) -> int:
        c = self._conn()
        cur = c.execute(sql, params)
        c.commit()
        return cur.rowcount

    def q(self, sql: str, params=()) -> List[sqlite3.Row]:
        return list(self._conn().execute(sql, params))

    def one(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        rows = self.q(sql, params)
        return rows[0] if rows else None


db = Database()


# ── ML Feedback & Model persistence helpers (new) ─────────────────────
def save_ml_feedback(email_id: str, features: dict, label: int = -1):
    """Store features and optionally a label for an email."""
    db.run(
        "INSERT OR REPLACE INTO ml_feedback (id, email_id, label, features, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), email_id, label, json.dumps(features), now_utc()),
    )


def get_ml_feedback(email_id: str) -> Tuple[Optional[dict], int]:
    """Retrieve stored features and label for an email. Returns (features_dict, label)."""
    row = db.one(
        "SELECT features, label FROM ml_feedback WHERE email_id=?", (email_id,)
    )
    if row:
        return json.loads(row["features"]), row["label"]
    return None, -1


def save_model_state(weights: dict, bias: float):
    """Persist the current ML model weights and bias."""
    db.run(
        "INSERT OR REPLACE INTO ml_model_state (id, weights, bias, updated_at) VALUES (?, ?, ?, ?)",
        ("singleton", json.dumps(weights), bias, now_utc()),
    )


def load_model_state() -> Tuple[Optional[dict], Optional[float]]:
    """Load the last saved model weights and bias. Returns (weights_dict, bias)."""
    row = db.one("SELECT weights, bias FROM ml_model_state WHERE id='singleton'")
    if row:
        return json.loads(row["weights"]), row["bias"]
    return None, None


# ── Provider Configs ───────────────────────────────────────────────────
PROVIDER_CONFIG = {
    "gmail": ("imap.gmail.com", 993, "smtp.gmail.com", 587, True),
    "outlook": ("outlook.office365.com", 993, "smtp.office365.com", 587, True),
    "yahoo": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587, True),
    "protonmail": ("127.0.0.1", 1143, "127.0.0.1", 1025, False),
    "custom": ("", 993, "", 587, True),
}

FOLDER_MAPPINGS = {
    "gmail": {
        "sent": ["[Gmail]/Sent Mail"],
        "drafts": ["[Gmail]/Drafts"],
        "trash": ["[Gmail]/Trash"],
        "archive": ["[Gmail]/All Mail"],
        "spam": ["[Gmail]/Spam"],
    },
    "outlook": {
        "sent": ["Sent Items"],
        "drafts": ["Drafts"],
        "trash": ["Deleted Items"],
        "archive": ["Archive"],
        "spam": ["Junk Email"],
    },
    "yahoo": {
        "sent": ["Sent"],
        "drafts": ["Draft"],
        "trash": ["Trash"],
        "archive": ["Archive"],
        "spam": ["Bulk Mail"],
    },
}


def get_folder_names(provider: str, folder_type: str) -> List[str]:
    mappings = FOLDER_MAPPINGS.get(provider.lower(), {})
    return mappings.get(folder_type, [folder_type.upper()])


# ── Data Models ────────────────────────────────────────────────────────
@dataclass
class Account:
    id: str
    user_id: str
    provider: str
    email: str
    display_name: str
    color: str
    enc_password: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    use_ssl: bool
    last_sync: str
    is_active: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row):
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            provider=row["provider"],
            email=row["email"],
            display_name=row["display_name"] or row["email"],
            color=row["color"] or "#4A9EFF",
            enc_password=row["enc_password"] or "",
            imap_host=row["imap_host"] or "",
            imap_port=row["imap_port"] or 993,
            smtp_host=row["smtp_host"] or "",
            smtp_port=row["smtp_port"] or 587,
            use_ssl=bool(row["use_ssl"]),
            last_sync=row["last_sync"] or "",
            is_active=bool(row["is_active"]),
        )


@dataclass
class EmailMsg:
    id: str
    account_id: str
    message_id: str
    uid: int
    folder: str
    category: str
    from_email: str
    from_name: str
    to_emails: str
    subject: str
    snippet: str
    body_text: str
    body_html: str
    date_sent: str
    is_read: bool
    is_starred: bool
    has_attachments: bool
    security_risk: str
    security_json: str

    @classmethod
    def from_row(cls, row: sqlite3.Row):
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            message_id=row["message_id"] or "",
            uid=row["uid"] or 0,
            folder=row["folder"] or "INBOX",
            category=row["category"] or "primary",
            from_email=row["from_email"] or "",
            from_name=row["from_name"] or "",
            to_emails=row["to_emails"] or "",
            subject=row["subject"] or "",
            snippet=row["snippet"] or "",
            body_text=row["body_text"] or "",
            body_html=row["body_html"] or "",
            date_sent=row["date_sent"] or "",
            is_read=bool(row["is_read"]),
            is_starred=bool(row["is_starred"]),
            has_attachments=bool(row["has_attachments"]),
            security_risk=row["security_risk"] or "unknown",
            security_json=row["security_json"] or "{}",
        )


@dataclass
class Contact:
    id: str
    user_id: str
    name: str
    email: str
    phone: str
    company: str
    notes: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row):
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"] or "",
            email=row["email"] or "",
            phone=row["phone"] or "",
            company=row["company"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"] or "",
        )


# ── Email Parser (uses normal_analysis from security_engine) ──────────
def _safe_bytes(raw) -> Optional[bytes]:
    """
    Guarantee we have a proper bytes object before passing to the email parser.
    Rejects integers, None, or strings that some IMAP servers may return.
    """
    if isinstance(raw, (bytes, bytearray)) and len(raw) > 16:
        return bytes(raw)
    return None


def parse_raw_email(
    raw_bytes, account_id: str, uid: int, folder: str
) -> Optional[dict]:
    # ── Guard: reject non-bytes input (integer from bad IMAP indexing, etc.) ──
    safe = _safe_bytes(raw_bytes)
    if safe is None:
        return None
    raw_bytes = safe

    try:
        msg = email_lib.message_from_bytes(raw_bytes)

        def safe_header(key: str, default: str = "") -> str:
            try:
                val = msg.get(key, default)
                if val:
                    decoded = email.header.decode_header(val)
                    parts = []
                    for content, charset in decoded:
                        if isinstance(content, (bytes, bytearray)):
                            parts.append(
                                content.decode(charset or "utf-8", errors="replace")
                            )
                        elif content is not None:
                            parts.append(str(content))
                    return " ".join(parts).strip()
                return default
            except Exception:
                return default

        def safe_payload_str(part) -> str:
            """Decode a MIME part payload to str, handling all edge cases."""
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    return ""
                if isinstance(payload, (bytes, bytearray)):
                    raw_p = bytes(payload)
                    enc = chardet.detect(raw_p).get("encoding", "utf-8") or "utf-8"
                    return raw_p.decode(enc, errors="replace")
                # Already a string (some edge-case parsers return str)
                return str(payload)
            except Exception:
                return ""

        message_id = safe_header("Message-ID")
        subject = safe_header("Subject", "(No Subject)")
        from_hdr = safe_header("From")
        to_hdr = safe_header("To")
        cc_hdr = safe_header("Cc")
        date_hdr = safe_header("Date")

        from_name, from_email = "", ""
        if from_hdr:
            try:
                from_name, from_email = email.utils.parseaddr(from_hdr)
            except Exception:
                from_email = from_hdr

        # ── Hardening: ensure from_email and from_name are strings ──
        if not isinstance(from_email, str):
            from_email = ""
        if not isinstance(from_name, str):
            from_name = ""

        date_sent = now_utc()
        if date_hdr:
            try:
                pd = email.utils.parsedate_to_datetime(date_hdr)
                if pd:
                    date_sent = pd.isoformat()
            except Exception:
                pass

        body_text = ""
        body_html = ""
        has_attachments = False
        _attachments_collected: list = []  # [{filename, content_type, data}]

        def extract_parts(part):
            nonlocal body_text, body_html, has_attachments
            try:
                ct = part.get_content_type()
                if ct == "text/plain" and not body_text:
                    body_text = safe_payload_str(part)
                elif ct == "text/html" and not body_html:
                    body_html = safe_payload_str(part)
                elif part.get_content_disposition() in ("attachment", "inline"):
                    filename = part.get_filename()
                    if filename:
                        has_attachments = True
                        # Safely get bytes for attachment storage
                        try:
                            raw_att = part.get_payload(decode=True)
                            att_bytes = (
                                bytes(raw_att)
                                if isinstance(raw_att, (bytes, bytearray))
                                else b""
                            )
                        except Exception:
                            att_bytes = b""
                        _attachments_collected.append(
                            {
                                "filename": filename,
                                "content_type": part.get_content_type()
                                or "application/octet-stream",
                                "data": att_bytes,
                            }
                        )
            except Exception as e:
                print(f"[Parser] Part error: {e}")

        if msg.is_multipart():
            for part in msg.walk():
                extract_parts(part)
        else:
            extract_parts(msg)

        snippet_src = body_text or (
            BeautifulSoup(body_html, "html.parser").get_text() if body_html else ""
        )
        snippet = re.sub(r"\s+", " ", snippet_src).strip()[:250]

        # -----------------------------------------------------------------
        # Use the enhanced security_engine.normal_analysis (single source of truth)
        # -----------------------------------------------------------------
        class _DummyEmail:
            """Minimal object that normal_analysis expects."""

            pass

        dummy = _DummyEmail()
        dummy.body_text = body_text
        dummy.body_html = body_html
        dummy.from_email = from_email
        dummy.from_name = from_name
        dummy.subject = subject
        dummy.has_attachments = has_attachments
        dummy.attachment_names = []  # We'll fill this later if needed
        # raw_headers is not used by normal_analysis but keep for completeness
        dummy.raw_headers = ""

        sec_result = normal_analysis(dummy)
        security_risk = sec_result["risk"]  # "safe", "suspicious", "dangerous"
        security_score = sec_result["score"]  # float 0..1
        security_json = json.dumps(sec_result)  # full analysis

        thread_id = message_id or str(uuid.uuid4())

        return {
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "message_id": message_id,
            "thread_id": thread_id,
            "uid": uid,
            "folder": folder,
            "category": "primary",
            "from_email": from_email,
            "from_name": from_name,
            "to_emails": to_hdr,
            "cc_emails": cc_hdr,
            "subject": subject,
            "snippet": snippet,
            "body_text": body_text,
            "body_html": body_html,
            "date_sent": date_sent,
            "is_read": 0,
            "is_starred": 0,
            "is_archived": 0,
            "is_deleted": 0,
            "is_draft": 1 if "draft" in folder.lower() else 0,
            "is_sent": 1 if "sent" in folder.lower() else 0,
            "has_attachments": 1 if has_attachments else 0,
            "security_risk": security_risk,
            "security_score": security_score,
            "security_json": security_json,
            "_attachments": _attachments_collected,  # saved to DB by sync loop
        }
    except Exception as e:
        print(f"[Parser] Fatal error: {e}")
        return None


# ── IMAP Syncer ────────────────────────────────────────────────────────
class IMAPSyncer:
    _DEFAULT_TIMEOUT = 30

    def __init__(self, account: Account, max_retries: int = 3):
        self.account = account
        self.max_retries = max_retries
        self.imap = None

    def connect(self) -> bool:
        """
        Establish IMAP SSL connection with retry + exponential back-off.
        """
        if not (self.account.imap_host or "").strip():
            print(f"[IMAP] Skipping {self.account.email}: no IMAP host configured.")
            return False

        timeout = self._DEFAULT_TIMEOUT

        for attempt in range(self.max_retries):
            try:
                password = (
                    decrypt(self.account.enc_password)
                    if self.account.enc_password
                    else ""
                )
                if not password:
                    print(f"[IMAP] No password for {self.account.email}")
                    return False

                ctx = ssl.create_default_context(cafile=certifi.where())

                self.imap = imaplib.IMAP4_SSL(
                    self.account.imap_host,
                    self.account.imap_port,
                    ssl_context=ctx,
                )
                self.imap.socket().settimeout(timeout)

                self.imap.login(self.account.email, password)

                print(f"[IMAP] Connected to {self.account.email} (attempt {attempt+1})")
                return True

            except imaplib.IMAP4.error as e:
                # Auth failures should not be retried – surface immediately
                err_str = str(e).upper()
                if any(
                    k in err_str for k in ("AUTH", "LOGIN", "CREDENTIALS", "INVALID")
                ):
                    print(f"[IMAP] Auth failure for {self.account.email}: {e}")
                    raise  # re-raise so workers.py maps it correctly
                print(f"[IMAP] IMAP error ({attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

            except ssl.SSLError as e:
                print(f"[IMAP] SSL error ({attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

            except OSError as e:
                print(f"[IMAP] Network error ({attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

            except Exception as e:
                print(f"[IMAP] Unexpected error ({attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        return False

    def disconnect(self):
        try:
            if self.imap:
                self.imap.logout()
        except Exception:
            pass
        finally:
            self.imap = None

    def _list_folders(self) -> List[str]:
        """Return all mailbox names from IMAP LIST, stripped of flags and delimiters."""
        try:
            status, data = self.imap.list()
            if status != "OK":
                return []
            names = []
            for item in data:
                if not item:
                    continue
                decoded = (
                    item.decode("utf-8", errors="replace")
                    if isinstance(item, bytes)
                    else item
                )
                # LIST response: (\Sent) "/" "Sent Messages"  OR  \Sent "/" Sent
                m = re.search(r'"([^"]+)"\s*$', decoded)
                if m:
                    names.append(m.group(1))
                else:
                    parts = decoded.rsplit(None, 1)
                    if parts:
                        names.append(parts[-1].strip('"'))
            return names
        except Exception as e:
            print(f"[IMAP] LIST error: {e}")
            return []

    def _select_folder(self, folder_names: List[str]) -> Optional[str]:
        """Try each name in order, return the first one that selects successfully."""
        for name in folder_names:
            try:
                status, _ = self.imap.select(f'"{name}"', readonly=True)
                if status == "OK":
                    return name
            except Exception:
                try:
                    status, _ = self.imap.select(name, readonly=True)
                    if status == "OK":
                        return name
                except Exception:
                    continue
        return None

    def _get_trash_folder_names(self) -> List[str]:
        """Discover trash folder names from the IMAP server, with a provider fallback."""
        try:
            status, data = self.imap.list()
            if status != "OK" or not data:
                return get_folder_names(self.account.provider, "trash")

            for line in data:
                if not line:
                    continue
                raw = (
                    line.decode("utf-8", errors="ignore")
                    if isinstance(line, (bytes, bytearray))
                    else str(line)
                )
                if "\\Trash" in raw or "trash" in raw.lower():
                    parts = raw.split(' "/" ')
                    if len(parts) == 2:
                        return [parts[1].strip('"')]
                    parts = raw.split(' "." ')
                    if len(parts) == 2:
                        return [parts[1].strip('"')]
        except Exception as e:
            print(f"[IMAP] Trash discovery error: {e}")

        return get_folder_names(self.account.provider, "trash")

    def sync(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        max_per_folder: int = 200,
    ) -> Tuple[List["EmailMsg"], int, List[str]]:
        if not self.connect():
            return [], 0, [f"Failed to connect to {self.account.email}"]

        messages: List[EmailMsg] = []
        total_new = 0
        errors: List[str] = []
        provider = self.account.provider.lower()

        folder_targets = [
            ("INBOX", ["INBOX"]),
            ("sent", get_folder_names(provider, "sent")),
            ("drafts", get_folder_names(provider, "drafts")),
            # 🔥 trash handled differently
            ("trash", self._get_trash_folder_names()),
        ]

        try:
            for folder_type, folder_names in folder_targets:
                selected = self._select_folder(folder_names)
                if not selected:
                    # ❗ IGNORE trash failures completely
                    if folder_type == "trash":
                        continue

                    errors.append(
                        f"Could not select {folder_type} (tried {folder_names})"
                    )
                    continue

                # Always use UID SEARCH for all providers.
                # Sequence numbers shift whenever messages are deleted, so the
                # duplicate-detection check (uid=? AND folder=?) would miss
                # already-stored messages and re-download them every sync.
                try:
                    status, uid_data = self.imap.uid("search", None, "ALL")
                    use_uid = True
                except Exception as search_err:
                    errors.append(f"Search failed in {selected}: {search_err}")
                    continue

                if status != "OK":
                    errors.append(f"Search failed in {selected}")
                    continue

                raw_ids = uid_data[0].split() if uid_data and uid_data[0] else []
                msg_ids = (
                    raw_ids[-max_per_folder:]
                    if len(raw_ids) > max_per_folder
                    else raw_ids
                )

                print(
                    f"[IMAP] {self.account.email} - {selected}: {len(msg_ids)} messages"
                )

                consecutive_failures = 0
                for idx, msg_num in enumerate(msg_ids, 1):
                    try:
                        if on_progress:
                            on_progress(idx, len(msg_ids), selected)

                        uid = int(msg_num)
                        existing = db.one(
                            "SELECT id FROM emails WHERE account_id=? AND uid=? AND folder=?",
                            (self.account.id, uid, folder_type),
                        )
                        if existing:
                            consecutive_failures = 0
                            continue

                        # Fetch using UID or sequence number
                        if use_uid:
                            status, data = self.imap.uid("fetch", msg_num, "(RFC822)")
                        else:
                            status, data = self.imap.fetch(msg_num, "(RFC822)")

                        if status != "OK" or not data:
                            consecutive_failures += 1
                            continue

                        # ── Safe multi-provider extraction ─────────────────
                        # IMAP FETCH/UID FETCH returns data in two shapes:
                        #   Tuple: [(b'1 (RFC822 {N})', b'<full email>'), b')']
                        #   Flat : [b'<full email>', b')']
                        # Always pick the LONGEST bytes item — that is the complete
                        # RFC822 message, not a partial header-like chunk.
                        raw_email: Optional[bytes] = None
                        best_len = 32  # ignore anything <= 32 bytes (flags/literals)
                        for item in data:
                            if isinstance(item, tuple) and len(item) >= 2:
                                candidate = item[1]
                                if (
                                    isinstance(candidate, (bytes, bytearray))
                                    and len(candidate) > best_len
                                ):
                                    raw_email = bytes(candidate)
                                    best_len = len(candidate)
                            elif isinstance(item, (bytes, bytearray)):
                                if len(item) > best_len:
                                    raw_email = bytes(item)
                                    best_len = len(item)

                        if not raw_email:
                            consecutive_failures += 1
                            continue

                        parsed = parse_raw_email(
                            raw_email, self.account.id, uid, folder_type
                        )
                        if not parsed:
                            consecutive_failures += 1
                            continue

                        # Reset failure counter on success
                        consecutive_failures = 0

                        db.run(
                            """INSERT OR IGNORE INTO emails(
                                id,account_id,message_id,thread_id,uid,folder,category,
                                from_email,from_name,to_emails,cc_emails,subject,snippet,
                                body_text,body_html,date_sent,is_read,is_starred,is_archived,
                                is_deleted,is_draft,is_sent,has_attachments,
                                security_risk,security_score,security_json
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                parsed["id"],
                                parsed["account_id"],
                                parsed["message_id"],
                                parsed["thread_id"],
                                parsed["uid"],
                                parsed["folder"],
                                parsed["category"],
                                parsed["from_email"],
                                parsed["from_name"],
                                parsed["to_emails"],
                                parsed["cc_emails"],
                                parsed["subject"],
                                parsed["snippet"],
                                parsed["body_text"],
                                parsed["body_html"],
                                parsed["date_sent"],
                                parsed["is_read"],
                                parsed["is_starred"],
                                parsed["is_archived"],
                                parsed["is_deleted"],
                                parsed["is_draft"],
                                parsed["is_sent"],
                                parsed["has_attachments"],
                                parsed["security_risk"],
                                parsed["security_score"],
                                parsed["security_json"],
                            ),
                        )

                        # ── Save attachment files to disk + DB ─────────
                        for att in parsed.get("_attachments", []):
                            try:
                                att_id = str(uuid.uuid4())
                                safe_name = re.sub(r"[^\w.\-]", "_", att["filename"])
                                att_path = ATTACH_DIR / att_id[:8] / safe_name
                                att_path.parent.mkdir(parents=True, exist_ok=True)
                                att_path.write_bytes(att["data"])
                                db.run(
                                    """INSERT OR IGNORE INTO attachments
                                       (id, email_id, filename, content_type,
                                        size_bytes, storage_path, is_inline)
                                       VALUES (?,?,?,?,?,?,0)""",
                                    (
                                        att_id,
                                        parsed["id"],
                                        att["filename"],
                                        att["content_type"],
                                        len(att["data"]),
                                        str(att_path),
                                    ),
                                )
                            except Exception as att_err:
                                print(f"[IMAP] Attachment save error: {att_err}")

                        # ── Collect for return value ───────────────────
                        messages.append(
                            EmailMsg(
                                id=parsed["id"],
                                account_id=parsed["account_id"],
                                message_id=parsed["message_id"],
                                uid=parsed["uid"],
                                folder=parsed["folder"],
                                category=parsed["category"],
                                from_email=parsed["from_email"],
                                from_name=parsed["from_name"],
                                to_emails=parsed["to_emails"],
                                subject=parsed["subject"],
                                snippet=parsed["snippet"],
                                body_text=parsed["body_text"],
                                body_html=parsed["body_html"],
                                date_sent=parsed["date_sent"],
                                is_read=bool(parsed["is_read"]),
                                is_starred=bool(parsed["is_starred"]),
                                has_attachments=bool(parsed["has_attachments"]),
                                security_risk=parsed["security_risk"],
                                security_json=parsed["security_json"],
                            )
                        )
                        total_new += 1

                    except imaplib.IMAP4.abort as e:
                        print(f"[IMAP] Connection aborted mid-folder ({selected}): {e}")
                        errors.append(
                            f"Connection lost in {selected} – partial sync saved"
                        )
                        break  # stop this folder; outer try handles reconnect if needed

                    except Exception as e:
                        print(f"[IMAP] Msg {msg_num} error: {e}")
                        consecutive_failures += 1
                        if consecutive_failures >= 10:
                            errors.append(
                                f"Too many consecutive fetch errors in {selected} – skipping remainder"
                            )
                            break

            db.run(
                "UPDATE accounts SET last_sync=? WHERE id=?",
                (now_utc(), self.account.id),
            )

        except imaplib.IMAP4.error as e:
            errors.append(f"IMAP error: {e}")
        except Exception as e:
            errors.append(f"Fatal sync error: {e}")
        finally:
            self.disconnect()

        return messages, total_new, errors


# ── SMTP Send ──────────────────────────────────────────────────────────
def send_email(
    account: Account,
    to_list,  # str or List[str]
    subject: str,
    body: str,
    cc: str = "",
    attachments: Optional[List[Tuple[str, bytes]]] = None,
    attachment_paths: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Send via SMTP.  Supports both STARTTLS (port 587) and SSL (port 465)."""
    try:
        password = decrypt(account.enc_password) if account.enc_password else ""
        if not password:
            return False, "No password configured"

        # Normalise recipients
        if isinstance(to_list, str):
            to_list = [
                a.strip() for a in to_list.replace(";", ",").split(",") if a.strip()
            ]
        if not to_list:
            return False, "No recipients specified"

        msg = MIMEMultipart()
        msg["From"] = (
            f"{account.display_name} <{account.email}>"
            if (account.display_name and account.display_name != account.email)
            else account.email
        )
        msg["To"] = ", ".join(to_list)
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=account.email.split("@")[-1])
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Inline attachments (List[Tuple[name, bytes]])
        if attachments:
            for filename, data in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
                msg.attach(part)

        # File-path attachments (List[str])
        if attachment_paths:
            for fpath in attachment_paths:
                p = Path(fpath)
                if not p.exists():
                    continue
                data = p.read_bytes()
                part = MIMEBase("application", "octet-stream")
                part.set_payload(data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", f'attachment; filename="{p.name}"'
                )
                msg.attach(part)

        port = account.smtp_port or 587
        all_recipients = list(to_list) + ([cc] if cc else [])

        # Port 465 uses SMTP_SSL; port 587 uses STARTTLS
        ctx = ssl.create_default_context(cafile=certifi.where())
        if port == 465:
            with smtplib.SMTP_SSL(
                account.smtp_host, port, context=ctx, timeout=30
            ) as srv:
                srv.login(account.email, password)
                srv.sendmail(account.email, all_recipients, msg.as_bytes())
        else:
            with smtplib.SMTP(account.smtp_host, port, timeout=30) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.ehlo()
                srv.login(account.email, password)
                srv.sendmail(account.email, all_recipients, msg.as_bytes())

        print(f"[SMTP] Sent from {account.email} to {all_recipients}")
        return True, ""
    except smtplib.SMTPAuthenticationError as e:
        return (
            False,
            f"Authentication failed – use an App Password for Gmail/Yahoo/Outlook. ({e})",
        )
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"Recipient refused: {e}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, str(e)


# ── Services ───────────────────────────────────────────────────────────
class TrustedSenderService:
    def is_trusted(self, user_id: str, email_addr: str) -> bool:
        row = db.one(
            "SELECT id FROM trusted_senders WHERE user_id=? AND pattern=? AND is_domain=0",
            (user_id, email_addr.lower()),
        )
        if row:
            return True
        domain = email_addr.split("@")[-1] if "@" in email_addr else ""
        if domain:
            row = db.one(
                "SELECT id FROM trusted_senders WHERE user_id=? AND pattern=? AND is_domain=1",
                (user_id, domain.lower()),
            )
            return bool(row)
        return False

    def add(self, user_id: str, pattern: str, is_domain: bool = False) -> bool:
        tid = str(uuid.uuid4())
        try:
            db.run(
                "INSERT INTO trusted_senders(id,user_id,pattern,is_domain,created_at) VALUES(?,?,?,?,?)",
                (tid, user_id, pattern.lower(), 1 if is_domain else 0, now_utc()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove(self, user_id: str, pattern: str):
        db.run(
            "DELETE FROM trusted_senders WHERE user_id=? AND pattern=?",
            (user_id, pattern.lower()),
        )

    def list_all(self, user_id: str) -> List[dict]:
        rows = db.q(
            "SELECT * FROM trusted_senders WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in rows]


class ContactService:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def create(
        self, name: str, email: str, phone: str = "", company: str = "", notes: str = ""
    ) -> Optional[Contact]:
        cid = str(uuid.uuid4())
        try:
            db.run(
                "INSERT INTO contacts(id,user_id,name,email,phone,company,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (cid, self.user_id, name, email, phone, company, notes, now_utc()),
            )
            return self.get(cid)
        except sqlite3.IntegrityError:
            return None

    def update(self, contact_id: str, **kwargs):
        fields, vals = [], []
        for k, v in kwargs.items():
            if k in ("name", "email", "phone", "company", "notes"):
                fields.append(f"{k}=?")
                vals.append(v)
        if fields:
            vals.append(contact_id)
            db.run(f"UPDATE contacts SET {','.join(fields)} WHERE id=?", vals)

    def delete(self, contact_id: str):
        db.run("DELETE FROM contacts WHERE id=?", (contact_id,))

    def get(self, contact_id: str) -> Optional[Contact]:
        row = db.one("SELECT * FROM contacts WHERE id=?", (contact_id,))
        return Contact.from_row(row) if row else None

    def find_by_email(self, email: str) -> Optional[Contact]:
        row = db.one(
            "SELECT * FROM contacts WHERE user_id=? AND email=?", (self.user_id, email)
        )
        return Contact.from_row(row) if row else None

    def list_all(self) -> List[Contact]:
        rows = db.q(
            "SELECT * FROM contacts WHERE user_id=? ORDER BY name", (self.user_id,)
        )
        return [Contact.from_row(r) for r in rows]

    def clear_all(self):
        db.run("DELETE FROM contacts WHERE user_id=?", (self.user_id,))


class UserService:
    def register(self, username: str, password: str, email: str = "") -> Optional[dict]:
        uid = str(uuid.uuid4())
        hashed = hash_password(password)
        try:
            db.run(
                "INSERT INTO users(id,username,email,hashed_pw,display_name,created_at) VALUES(?,?,?,?,?,?)",
                (uid, username.lower(), email.lower(), hashed, username, now_utc()),
            )
            return {"id": uid, "username": username, "email": email}
        except sqlite3.IntegrityError:
            return None

    def login(self, username: str, password: str) -> Optional[dict]:
        row = db.one(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username.lower(), username.lower()),
        )
        if not row or not verify_password(password, row["hashed_pw"]):
            return None
        log_id = str(uuid.uuid4())
        cur_time = now_utc()
        db.run(
            "INSERT INTO login_logs(id,user_id,login_time,ip) VALUES(?,?,?,?)",
            (log_id, row["id"], cur_time, "local"),
        )
        db.run("UPDATE users SET last_login=? WHERE id=?", (cur_time, row["id"]))
        return dict(row)

    def get_login_logs(self, user_id: str) -> List[dict]:
        rows = db.q(
            "SELECT login_time,ip FROM login_logs WHERE user_id=? ORDER BY login_time DESC LIMIT 20",
            (user_id,),
        )
        return [{"time": r["login_time"], "ip": r["ip"]} for r in rows]


class AccountService:
    def test_connection(
        self,
        provider: str,
        email: str,
        password: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> Tuple[bool, str]:
        cfg = PROVIDER_CONFIG.get(provider, ("", 993, "", 587, True))
        ih = imap_host or cfg[0]
        ip_ = imap_port or cfg[1]
        if not ih:
            return False, "Missing IMAP server details."
        try:
            ctx = ssl.create_default_context(cafile=certifi.where())
            imap = imaplib.IMAP4_SSL(ih, int(ip_), ssl_context=ctx)
            imap.socket().settimeout(10)
            imap.login(email, password)
            imap.logout()
            return True, "Connection successful! ✅"
        except imaplib.IMAP4.error:
            return False, "Authentication failed. Use app-specific password."
        except Exception as e:
            return False, f"Connection failed: {e}"

    def add_account(
        self,
        user_id: str,
        provider: str,
        email: str,
        password: str = "",
        display_name: str = "",
        color: str = "#4A9EFF",
        imap_host: str = "",
        imap_port: int = 993,
        smtp_host: str = "",
        smtp_port: int = 587,
    ) -> Optional[Account]:
        aid = str(uuid.uuid4())
        cfg = PROVIDER_CONFIG.get(provider, ("", 993, "", 587, True))
        ih = imap_host or cfg[0]
        ip_ = imap_port or cfg[1]
        sh = smtp_host or cfg[2]
        sp = smtp_port or cfg[3]
        enc_pw = encrypt(password) if password else ""
        try:
            db.run(
                """INSERT INTO accounts(id,user_id,provider,email,display_name,color,
                   enc_password,imap_host,imap_port,smtp_host,smtp_port,notifications_enabled)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    aid,
                    user_id,
                    provider,
                    email.lower(),
                    display_name or email,
                    color,
                    enc_pw,
                    ih,
                    ip_,
                    sh,
                    sp,
                    1,
                ),
            )
            return self.get(aid)
        except sqlite3.IntegrityError:
            return None

    # alias
    def create_account(
        self,
        user_id: str,
        email: str,
        provider: str,
        password: str,
        display_name: str = "",
        color: str = "#4A9EFF",
    ) -> Optional[Account]:
        return self.add_account(user_id, provider, email, password, display_name, color)

    def update_account(self, account_id: str, **kwargs) -> bool:
        fields, vals = [], []
        for k, v in kwargs.items():
            if k in (
                "display_name",
                "color",
                "notifications_enabled",
                "provider",
                "email",
            ):
                fields.append(f"{k}=?")
                vals.append(v)
            elif k == "password":
                fields.append("enc_password=?")
                vals.append(encrypt(v) if v else "")
        if not fields:
            return False
        vals.append(account_id)
        db.run(f"UPDATE accounts SET {','.join(fields)} WHERE id=?", vals)
        return True

    def delete_account(self, account_id: str) -> bool:
        db.run("UPDATE accounts SET is_active=0 WHERE id=?", (account_id,))
        return True

    def get(self, account_id: str) -> Optional[Account]:
        row = db.one("SELECT * FROM accounts WHERE id=? AND is_active=1", (account_id,))
        return Account.from_row(row) if row else None

    def list_for_user(self, user_id: str) -> List[Account]:
        rows = db.q(
            "SELECT * FROM accounts WHERE user_id=? AND is_active=1", (user_id,)
        )
        return [Account.from_row(r) for r in rows]

    def update_notification(self, account_id: str, enabled: bool):
        db.run(
            "UPDATE accounts SET notifications_enabled=? WHERE id=?",
            (1 if enabled else 0, account_id),
        )


class EmailService:
    def list_emails(
        self,
        account_ids: List[str],
        folder: str = "INBOX",
        category: str = "",
        search: str = "",
        is_starred: Optional[bool] = None,
        security_risk: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[EmailMsg], int]:
        if not account_ids:
            return [], 0

        ph = ",".join("?" * len(account_ids))
        cnd = [f"account_id IN ({ph})", "is_deleted=0"]
        par: list = list(account_ids)

        if folder == "INBOX":
            cnd += ["folder='INBOX'", "is_archived=0"]
        elif folder:
            cnd.append(f"folder=?")
            par.append(folder)

        if category:
            cnd.append("category=?")
            par.append(category)
        if security_risk:
            cnd.append("security_risk=?")
            par.append(security_risk)
        if is_starred is True:
            cnd.append("is_starred=1")
        if search:
            cnd.append(
                "(subject LIKE ? OR from_email LIKE ? OR snippet LIKE ? OR body_text LIKE ?)"
            )
            s = f"%{search}%"
            par += [s, s, s, s]

        where = " AND ".join(cnd)
        total_row = db.one(f"SELECT COUNT(*) FROM emails WHERE {where}", par)
        total = total_row[0] if total_row else 0

        off = (page - 1) * page_size
        rows = db.q(
            f"SELECT * FROM emails WHERE {where} ORDER BY date_sent DESC LIMIT ? OFFSET ?",
            par + [page_size, off],
        )
        return [EmailMsg.from_row(r) for r in rows], total

    def get(self, email_id: str, user_account_ids: List[str]) -> Optional[EmailMsg]:
        ph = ",".join("?" * len(user_account_ids))
        row = db.one(
            f"SELECT * FROM emails WHERE id=? AND account_id IN ({ph})",
            [email_id] + user_account_ids,
        )
        if not row:
            return None
        em = EmailMsg.from_row(row)
        if not em.is_read:
            db.run("UPDATE emails SET is_read=1 WHERE id=?", (email_id,))
            em.is_read = True
        return em

    def mark_read(self, email_ids: List[str], read: bool):
        if not email_ids:
            return
        ph = ",".join("?" * len(email_ids))
        db.run(
            f"UPDATE emails SET is_read=? WHERE id IN ({ph})",
            [1 if read else 0] + email_ids,
        )

    def mark_starred(self, email_ids: List[str], starred: bool):
        if not email_ids:
            return
        ph = ",".join("?" * len(email_ids))
        db.run(
            f"UPDATE emails SET is_starred=? WHERE id IN ({ph})",
            [1 if starred else 0] + email_ids,
        )

    def delete_email(self, eid: str):
        db.run("UPDATE emails SET is_deleted=1, folder='Trash' WHERE id=?", (eid,))

    def update_security_risk(self, email_id: str, risk: str):
        db.run("UPDATE emails SET security_risk=? WHERE id=?", (risk, email_id))

    def unread_counts(self, account_ids: List[str]) -> Dict[str, int]:
        if not account_ids:
            return {}
        ph = ",".join("?" * len(account_ids))
        rows = db.q(
            f"SELECT folder, COUNT(*) c FROM emails "
            f"WHERE account_id IN ({ph}) AND is_read=0 AND is_deleted=0 GROUP BY folder",
            account_ids,
        )
        return {r["folder"]: r["c"] for r in rows}

    def security_stats(self, account_ids: List[str]) -> dict:
        if not account_ids:
            return {}
        ph = ",".join("?" * len(account_ids))
        rows = db.q(
            f"SELECT security_risk, COUNT(*) c FROM emails "
            f"WHERE account_id IN ({ph}) GROUP BY security_risk",
            account_ids,
        )
        return {r["security_risk"]: r["c"] for r in rows}


# ── Exported service instances ─────────────────────────────────────────
user_svc = UserService()
account_svc = AccountService()
email_svc = EmailService()
trusted_svc = TrustedSenderService()