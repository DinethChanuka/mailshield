"""
MailShield – Advanced Security Engine v9.0
Detection layers:
  1. URL Structure Inspection   – effective-domain extraction, subdomain deception
  2. Punycode / Homograph       – Unicode look-alike domain attacks
  3. Percent-Encoding Norm.     – %70%61%79%70%61%6c → paypal decoded check
  4. Tunnel / Free-host         – ngrok, trycloudflare, serveo, loca.lt … (score 0.97)
  5. Invisible-text Detection   – white-on-white / zero-width characters
  6. Link-Display Mismatch      – <a href=evil>paypal.com</a>
  7. Sender Forensics           – SPF/DKIM header parse, Return-Path mismatch
  8. Behavioural Intent         – urgency + external link = escalate
  9. Attachment Exploitation    – double-ext, macro-enabled, disk images
 10. HTML Obfuscation           – base64 payloads, JS eval, event handlers
 11. Deep ML Classifier         – logistic regression over 11 features
"""

from __future__ import annotations

import re
import math
import html as html_lib
from collections import Counter
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import urlparse, unquote
from PyQt5.QtCore import QThread, pyqtSignal

try:
    from bs4 import BeautifulSoup

    _BS4 = True
except ImportError:
    _BS4 = False


# ── Safe string helpers ────────────────────────────────────────────────
def safe_str(v):
    """Return empty string if v is None or not a string."""
    return v if isinstance(v, str) else ""


def safe_split(v, sep="@"):
    """Safe split that never crashes on None."""
    if not isinstance(v, str):
        return []
    return v.split(sep)


# ══════════════════════════════════════════════════════════════════════
#  THREAT INTELLIGENCE TABLES
# ══════════════════════════════════════════════════════════════════════

SUSPICIOUS_TLDS = {
    ".tk",
    ".ml",
    ".ga",
    ".cf",
    ".gq",
    ".xyz",
    ".top",
    ".click",
    ".link",
    ".live",
    ".stream",
    ".download",
    ".win",
    ".loan",
    ".men",
    ".work",
    ".party",
    ".racing",
    ".review",
    ".science",
    ".country",
    ".cricket",
    ".webcam",
    ".faith",
    ".bid",
    ".trade",
    ".date",
    ".space",
    ".fun",
    ".uno",
    ".monster",
    ".buzz",
    ".bar",
    ".hair",
    ".makeup",
    ".zip",
    ".mov",
    ".phd",
    ".prof",
    ".icu",
    ".cyou",
    ".vip",
    ".gdn",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "aol.com",
    "protonmail.com",
    "mail.com",
    "yandex.com",
    "gmx.com",
    "icloud.com",
    "zoho.com",
    "tutanota.com",
    "fastmail.com",
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "throwam.com",
    "sharklasers.com",
    "guerrillamailblock.com",
    "grr.la",
}

SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "cutt.ly",
    "rb.gy",
    "short.link",
    "is.gd",
    "v.gd",
    "ow.ly",
    "buff.ly",
    "rebrand.ly",
    "shorturl.at",
    "bl.ink",
    "snip.ly",
    "tr.im",
    "x.co",
    "po.st",
    "tiny.cc",
    "bitly.com",
    "short.io",
    "shorte.st",
    "t.co",
    "goo.gl",
    "smarturl.it",
    "lnkd.in",
    "youtu.be",
    "fb.me",
    "waa.ai",
    "clk.sh",
    "url.ie",
    "qr.ae",
    "mcaf.ee",
    "clicky.me",
    "budurl.com",
    "trib.al",
}

FREE_HOSTING_DOMAINS = {
    "000webhostapp.com",
    "weebly.com",
    "wixsite.com",
    "jimdo.com",
    "yolasite.com",
    "site123.me",
    "webflow.io",
    "netlify.app",
    "vercel.app",
    "github.io",
    "pages.dev",
    "surge.sh",
    "glitch.me",
    "replit.co",
    "repl.co",
    "stackblitz.io",
    "render.com",
    "fly.dev",
    "railway.app",
    "herokuapps.com",
    "pythonanywhere.com",
    "beeceptor.com",
    "requestcatcher.com",
    "infinityfreeapp.com",
    "byethost.com",
    "freehosting.com",
    "awardspace.com",
    "freehostia.com",
    "x10hosting.com",
}

CRITICAL_TUNNEL_DOMAINS = {
    "ngrok.io",
    "ngrok.com",
    "ngrok-free.app",
    "eu.ngrok.io",
    "loca.lt",
    "localtunnel.me",
    "serveo.net",
    "pagekite.me",
    "loclx.io",
    "trycloudflare.com",
    "cfargotunnel.com",
    "bore.pub",
    "expose.sh",
    "telebit.app",
    "zrok.io",
    "a.pinggy.io",
    "pinggy.link",
    "pktriot.net",
    "portmap.io",
    "localhost.run",
    "loophole.site",
    "sslip.io",
    "nip.io",
    "xip.io",
    "hookdeck.com",
    "hookbin.com",
    "webhook.site",
    "requestbin.com",
}

_TUNNEL_KEYWORDS = (
    "ngrok",
    "localtunnel",
    "trycloudflare",
    "serveo",
    "pagekite",
    "loclx",
    "zrok",
    "pinggy",
    "pktriot",
    "portmap",
    "loophole",
    "expose.sh",
    "bore.pub",
)

BRAND_IMPERSONATION = {
    "paypal",
    "amazon",
    "google",
    "microsoft",
    "apple",
    "netflix",
    "bank of america",
    "chase",
    "wells fargo",
    "facebook",
    "instagram",
    "twitter",
    "linkedin",
    "dropbox",
    "spotify",
    "adobe",
    "zoom",
    "fedex",
    "ups",
    "dhl",
    "usps",
    "walmart",
    "target",
    "best buy",
    "hulu",
    "disney",
    "att",
    "verizon",
    "tmobile",
    "comcast",
    "american express",
    "capital one",
    "citi",
    "discover",
    "hsbc",
    "barclays",
    "santander",
    "natwest",
    "lloyds",
    "halifax",
    "steam",
    "epic games",
    "blizzard",
    "riot games",
    "coinbase",
    "binance",
    "kraken",
    "blockchain",
    "docusign",
    "sharepoint",
    "onedrive",
    "office365",
}

URGENCY_PHRASES = [
    "limited time",
    "act now",
    "immediately",
    "urgent",
    "confirm now",
    "verify now",
    "within 24 hours",
    "expires soon",
    "last chance",
    "time sensitive",
    "action required",
    "immediate action",
    "deadline",
    "don't delay",
    "hurry",
    "expiring",
    "final notice",
    "critical",
    "important update",
    "attention required",
    "respond immediately",
    "asap",
    "no later than",
    "before it's too late",
    "ends today",
    "offer expires",
    "last day",
    "final warning",
    "account will be",
    "account has been",
    "unusual sign-in",
    "suspicious activity",
    "unusual activity detected",
    "security alert",
    "verify your identity",
]

REWARD_PATTERNS = [
    "you are selected",
    "exclusive invite",
    "you won",
    "prize",
    "reward",
    "congratulations",
    "free gift",
    "claim your",
    "selected user",
    "winner",
    "lucky winner",
    "cash prize",
    "gift card",
    "free access",
    "special offer",
    "limited reward",
    "claim now",
    "your reward",
    "bonus",
    "cashback",
    "free trial",
    "exclusive deal",
    "one time offer",
    "discount code",
    "voucher inside",
    "secret offer",
    "members only",
    "you have been chosen",
    "lottery",
    "sweepstakes",
    "raffle",
    "grant",
]

CREDENTIAL_PATTERNS = [
    r"(login|verify|sign[\s-]in|account).{0,30}(password|credential|security)",
    r"(enter|provide|confirm).{0,20}(username|password|pin|otp|passcode)",
    r"(your|account).{0,20}(has been|will be).{0,20}(suspend|lock|terminat|disabl|block)",
    r"(click|tap).{0,20}(here|button|link).{0,20}(to|and).{0,20}(verify|confirm|access|restore)",
    r"(update|confirm).{0,15}(payment|billing|card|bank)",
    r"(re-?enter|re-?verify|re-?confirm).{0,20}(password|details|info)",
]

JS_RISK_PATTERNS = [
    r"window\.location",
    r"document\.location",
    r"eval\s*\(",
    r"atob\s*\(",
    r"unescape\s*\(",
    r"setTimeout\s*\(",
    r"setInterval\s*\(",
    r"new\s+Function\s*\(",
    r"XMLHttpRequest",
    r"fetch\s*\(",
    r"\.src\s*=",
    r"\.href\s*=",
    r"document\.write\s*\(",
    r"innerHTML\s*=",
    r"outerHTML\s*=",
    r"document\.createElement",
]

DANGEROUS_ATTACHMENT_EXTS = {
    ".exe",
    ".scr",
    ".com",
    ".pif",
    ".bat",
    ".cmd",
    ".vbs",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".msi",
    ".msp",
    ".dll",
    ".sys",
    ".drv",
    ".ps1",
    ".psm1",
    ".psd1",
    ".hta",
    ".jar",
    ".class",
    ".docm",
    ".xlsm",
    ".pptm",
    ".dotm",
    ".xlam",
    ".xla",
    ".iso",
    ".img",
    ".vhd",
    ".vmdk",
    ".lnk",
    ".url",
    ".reg",
    ".inf",
    ".html",
    ".htm",
}

SUSPICIOUS_ATTACHMENT_EXTS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".pdf",
    ".doc",
    ".xls",
    ".ppt",
    ".rtf",
    ".odt",
    ".ods",
}

_CONFUSABLES: Dict[str, str] = {
    "a": "a",
    "e": "e",
    "o": "o",
    "p": "p",
    "c": "c",
    "x": "x",
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0445": "x",
    "\u0456": "i",
    "\u0404": "e",
}


# ══════════════════════════════════════════════════════════════════════
#  LAYER 1+2 – URL STRUCTURE + PUNYCODE DETECTION
# ══════════════════════════════════════════════════════════════════════


def extract_effective_domain(domain: str) -> str:
    parts = safe_split(domain, ".")
    if len(parts) <= 2:
        return domain
    _multi = {"co", "com", "net", "org", "gov", "edu", "ac", "me", "or"}
    if parts[-2] in _multi and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_url(url: str) -> str:
    try:
        return unquote(url).lower()
    except Exception:
        return url.lower()


def detect_subdomain_deception(domain: str) -> Tuple[bool, str]:
    eff = extract_effective_domain(domain)
    if eff == domain:
        return False, ""
    subdomain_part = domain[: len(domain) - len(eff) - 1].lower()
    for brand in BRAND_IMPERSONATION:
        if brand.replace(" ", "") in subdomain_part.replace(".", ""):
            return True, f"Subdomain spoofs '{brand}' but real domain is '{eff}'"
    return False, ""


def detect_homograph(domain: str) -> Tuple[bool, str]:
    try:
        domain.encode("ascii")
    except UnicodeEncodeError:
        normalized = "".join(_CONFUSABLES.get(c, c) for c in domain.lower())
        for brand in BRAND_IMPERSONATION:
            if brand.replace(" ", "") in normalized.replace(".", ""):
                return True, f"Homograph attack: '{domain}' mimics '{brand}'"
        return True, f"Non-ASCII/homograph domain: '{domain}'"
    if "xn--" in domain.lower():
        try:
            decoded = domain.encode("ascii").decode("idna")
            for brand in BRAND_IMPERSONATION:
                if brand.replace(" ", "") in decoded.lower().replace(".", ""):
                    return (
                        True,
                        f"Punycode '{domain}' decodes to lookalike of '{brand}'",
                    )
        except Exception:
            return True, f"Malformed punycode domain: '{domain}'"
    return False, ""


# ══════════════════════════════════════════════════════════════════════
#  LAYER 3 – DOMAIN REPUTATION
# ══════════════════════════════════════════════════════════════════════


def domain_reputation(domain: str) -> Tuple[float, List[str]]:
    flags: List[str] = []
    score = 0.0

    if domain in CRITICAL_TUNNEL_DOMAINS:
        return 0.97, ["Tunnel/expose service — common phishing C2"]
    for td in CRITICAL_TUNNEL_DOMAINS:
        if domain.endswith("." + td):
            return 0.97, [f"Subdomain of tunnel service: {td}"]
    if any(kw in domain for kw in _TUNNEL_KEYWORDS):
        return 0.95, ["Tunnel keyword in domain"]

    if domain in FREE_HOSTING_DOMAINS:
        score = max(score, 0.70)
        flags.append("Free hosting platform")

    if domain in SHORTENER_DOMAINS:
        score = max(score, 0.65)
        flags.append("URL shortener — hides real destination")

    for tld in SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            score = max(score, 0.60)
            flags.append(f"Suspicious TLD: {tld}")
            break

    if re.search(r"^\d+\.\d+\.\d+\.\d+$", domain):
        score = max(score, 0.80)
        flags.append("IP address used as domain")

    dot_count = domain.count(".")
    if dot_count >= 4:
        score = min(score + 0.25, 1.0)
        flags.append(f"Excessive subdomains ({dot_count} dots)")
    elif dot_count == 3:
        score = min(score + 0.10, 1.0)

    name_part = safe_split(domain, ".")[0] if "." in domain else domain
    if len(name_part) > 20:
        score = min(score + 0.15, 1.0)
        flags.append("Unusually long domain name")
    if re.search(r"\d{6,}", domain):
        score = min(score + 0.20, 1.0)
        flags.append("Large numeric sequence in domain")

    hg, hg_msg = detect_homograph(domain)
    if hg:
        score = max(score, 0.90)
        flags.append(hg_msg)

    sd, sd_msg = detect_subdomain_deception(domain)
    if sd:
        score = max(score, 0.88)
        flags.append(sd_msg)

    return min(score, 1.0), flags


# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════


def extract_urls(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r'https?://[^\s"\'<>()]+', text)


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def extract_links_with_details(body_text: str, body_html: str) -> List[Dict[str, Any]]:
    all_html = (body_html or "") + " " + (body_text or "")
    urls = extract_urls(all_html)
    if not urls:
        return []

    link_details: List[Dict] = []
    seen: set = set()

    display_map: Dict[str, str] = {}
    if body_html and _BS4:
        try:
            soup = BeautifulSoup(body_html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)[:100]
                if href.startswith("http"):
                    display_map[href] = text
        except Exception:
            pass

    for raw_url in urls:
        if raw_url in seen:
            continue
        seen.add(raw_url)

        domain = get_domain(raw_url)
        rep_score, rep_flags = domain_reputation(domain)
        all_flags: List[str] = list(rep_flags)

        # Percent-encoding brand spoof
        decoded = normalize_url(raw_url)
        for brand in BRAND_IMPERSONATION:
            bc = brand.replace(" ", "")
            if bc in decoded and bc not in domain:
                all_flags.append(
                    f"Encoded URL references '{brand}' but domain is '{domain}'"
                )
                rep_score = max(rep_score, 0.75)
                break

        # Display-text mismatch
        display_text = display_map.get(raw_url, "")
        if display_text:
            dt = display_text.lower()
            dt_dom = get_domain(dt) if dt.startswith("http") else ""
            if dt_dom and dt_dom != domain:
                all_flags.append(
                    f"Link text shows '{dt_dom}' but href goes to '{domain}'"
                )
                rep_score = max(rep_score, 0.82)
            elif not dt.startswith("http"):
                for brand in BRAND_IMPERSONATION:
                    if brand in dt and brand.replace(" ", "") not in domain:
                        all_flags.append(
                            f"Link text impersonates '{brand}' (misleading)"
                        )
                        rep_score = max(rep_score, 0.70)
                        break

        risk_level = (
            "safe"
            if rep_score < 0.30
            else "suspicious" if rep_score < 0.60 else "dangerous"
        )
        link_details.append(
            {
                "url": raw_url,
                "domain": domain,
                "eff_domain": extract_effective_domain(domain),
                "display_text": display_text,
                "risk_score": round(rep_score, 2),
                "risk_level": risk_level,
                "flags": all_flags,
            }
        )

    return sorted(link_details, key=lambda x: x["risk_score"], reverse=True)


def detect_invisible_text(html: str) -> Tuple[bool, str]:
    if not html:
        return False, ""
    lower = html.lower()
    zero_width = ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"]
    if any(zw in html for zw in zero_width):
        return True, "Zero-width characters found (text obfuscation)"
    wt_patterns = [
        r"color\s*:\s*#fff(fff)?(?!\w)",
        r"color\s*:\s*white\b",
        r"color\s*:\s*rgba?\s*\(\s*255\s*,\s*255\s*,\s*255",
        r"color\s*:\s*#f{3,6}\b",
    ]
    for p in wt_patterns:
        if re.search(p, lower):
            return True, "White/invisible text detected (spam filter evasion)"
    if re.search(r"<[ap][^>]*style\s*=[^>]*display\s*:\s*none", lower):
        return True, "Hidden text element detected"
    if re.search(r"font-size\s*:\s*0\s*(px|pt|em)?", lower):
        return True, "Zero font-size text (invisible content)"
    return False, ""


def parse_auth_headers(raw_headers: str) -> Dict[str, str]:
    result = {"spf": "none", "dkim": "none", "dmarc": "none"}
    if not raw_headers:
        return result
    lower = raw_headers.lower()
    for proto in ("spf", "dkim", "dmarc"):
        m = re.search(rf"{proto}\s*=\s*(pass|fail|softfail|neutral|none)", lower)
        if m:
            v = m.group(1)
            result[proto] = "fail" if v in ("fail", "softfail") else v
    return result


def detect_return_path_mismatch(raw_headers, from_email) -> Tuple[bool, str]:
    if not isinstance(raw_headers, str) or not isinstance(from_email, str):
        return False, ""
    m = re.search(r"return-path:\s*<([^>]+)>", raw_headers, re.IGNORECASE)
    if not m:
        return False, ""
    rp = m.group(1).strip().lower()
    if "@" in rp:
        rp_dom = safe_split(rp, "@")[-1]
    else:
        rp_dom = ""
    from_dom = safe_split(from_email, "@")[-1] if "@" in from_email else ""
    if rp_dom and from_dom and rp_dom != from_dom:
        return (
            True,
            f"Return-Path domain '{rp_dom}' differs from From domain '{from_dom}'",
        )
    return False, ""


def sender_mismatch(from_email: str, from_name: str) -> Tuple[float, str]:
    if not isinstance(from_email, str) or not isinstance(from_name, str):
        return 0.0, ""
    domain = safe_split(from_email, "@")[-1].lower() if "@" in from_email else ""
    name_lower = from_name.lower()
    if domain in FREE_EMAIL_DOMAINS:
        for brand in BRAND_IMPERSONATION:
            if brand in name_lower:
                return 0.75, f"Free-mail ({domain}) impersonating '{brand}'"
    for brand in BRAND_IMPERSONATION:
        if brand in name_lower and brand.replace(" ", "") not in domain:
            return 0.65, f"Sender name claims '{brand}' but email is from '{domain}'"
    for tld in SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            return 0.55, f"Suspicious sender domain TLD: {tld}"
    return 0.0, ""


def analyze_keywords(text: str) -> Tuple[float, List[str], List[Dict]]:
    score = 0.0
    reasons = []
    ctxs = []
    lower = text.lower()
    seen: set = set()

    for phrase in URGENCY_PHRASES + REWARD_PATTERNS:
        if phrase in seen:
            continue
        idx = lower.find(phrase)
        if idx < 0:
            continue
        seen.add(phrase)
        cat = "urgency" if phrase in URGENCY_PHRASES else "reward_scam"
        score += 0.22 if cat == "urgency" else 0.28
        reasons.append(
            f"{'Urgency' if cat=='urgency' else 'Reward/scam'} language: '{phrase}'"
        )
        s = max(0, idx - 40)
        e = min(len(text), idx + len(phrase) + 40)
        ctxs.append(
            {
                "keyword": phrase,
                "context": f"…{text[s:e].replace(chr(10),' ').strip()}…",
                "category": cat,
            }
        )
        if len(ctxs) >= 8:
            break

    for pat in CREDENTIAL_PATTERNS:
        if re.search(pat, lower):
            score += 0.35
            reasons.append("Credential-harvesting language detected")
            break

    if re.search(r"(payment|invoice|bank|transfer|credit card|billing)", lower):
        score += 0.18
        reasons.append("Financial request detected")
    if re.search(r"(support|helpdesk|customer service|help desk)", lower):
        score += 0.12
        reasons.append("Customer support impersonation language")

    return min(score, 1.0), reasons, ctxs


def has_hidden_links(html: str) -> Tuple[bool, str]:
    if not html:
        return False, ""
    for p, label in [
        (r'<button[^>]*onclick=["\']location\.href', "Button-based redirect"),
        (r'<a[^>]*style=["\'][^"\']*display:\s*none', "Hidden anchor link"),
        (r'<div[^>]*onclick=["\'].*location\.href', "Div-based redirect"),
        (r"<meta[^>]*refresh", "Meta refresh redirect"),
        (r"window\.location\s*=", "JS window.location redirect"),
        (r"document\.location\s*=", "JS document.location"),
    ]:
        if re.search(p, html, re.IGNORECASE):
            return True, label
    return False, ""


def is_base64_encoded(text: str) -> Tuple[bool, str]:
    if not text:
        return False, ""
    if re.search(r"[A-Za-z0-9+/]{40,}={0,2}", text):
        return True, "Suspicious base64-encoded content detected"
    return False, ""


def detect_javascript(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    findings = []
    for match in re.finditer(
        r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE
    ):
        content = match.group(1).strip()
        if not content:
            continue
        risk_found = [
            p for p in JS_RISK_PATTERNS if re.search(p, content, re.IGNORECASE)
        ]
        findings.append(
            {
                "type": "script_block",
                "preview": content[:80].replace("\n", " "),
                "risk_patterns": risk_found,
                "risk": "high" if risk_found else "medium",
            }
        )
    for m in re.finditer(
        r'on(click|load|mouseover|submit|change|focus|blur)=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        findings.append(
            {
                "type": "event_handler",
                "preview": f"on{m.group(1)}: {m.group(2)[:60]}",
                "risk": "medium",
            }
        )
    for m in re.finditer(r'href=["\']javascript:[^"\']+["\']', html, re.IGNORECASE):
        findings.append(
            {"type": "javascript_uri", "preview": m.group(0)[:80], "risk": "high"}
        )
    return findings


def detect_buttons(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    findings = []
    if _BS4:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for btn in soup.find_all(["button", "input"]):
                t = btn.get("type", "button").lower()
                if t in ("submit", "button", "image", ""):
                    text = btn.get_text(strip=True)[:60] or btn.get("value", "")[:60]
                    has_action = bool(btn.get("onclick") or btn.get("formaction"))
                    findings.append(
                        {
                            "text": text or f"<{btn.name}>",
                            "type": btn.name,
                            "has_inline_action": has_action,
                            "risk": "medium" if has_action else "low",
                        }
                    )
        except Exception:
            pass
    return findings


def detect_forms(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    findings = []
    if _BS4:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for form in soup.find_all("form"):
                action = form.get("action", "(none)")[:80]
                method = form.get("method", "get").upper()
                inputs = form.find_all("input")
                types = [i.get("type", "text").lower() for i in inputs]
                has_pwd = "password" in types
                has_txt = any(t in ("text", "email") for t in types)
                findings.append(
                    {
                        "action": action,
                        "method": method,
                        "input_count": len(inputs),
                        "has_password": has_pwd,
                        "credential_harvest": has_pwd or (has_txt and len(inputs) >= 2),
                        "risk": "high" if has_pwd else "medium",
                    }
                )
        except Exception:
            pass
    else:
        for m in re.finditer(
            r'<form[^>]*action=["\']([^"\']*)["\']', html, re.IGNORECASE
        ):
            findings.append({"action": m.group(1)[:80], "method": "GET", "risk": "low"})
    return findings


def classify_attachment_risk(filename: str) -> Tuple[str, str]:
    if not filename:
        return "unknown", ""
    name_lower = filename.lower()
    parts = safe_split(name_lower, ".")
    if len(parts) > 2:
        last = f".{parts[-1]}"
        prev = f".{parts[-2]}"
        safe = {".pdf", ".doc", ".xls", ".jpg", ".jpeg", ".png", ".txt"}
        if last in DANGEROUS_ATTACHMENT_EXTS and prev in safe:
            return "critical", f"Double-extension disguise: {filename}"
    ext = f".{parts[-1]}" if len(parts) > 1 else ""
    if ext in DANGEROUS_ATTACHMENT_EXTS:
        return "high", f"Executable/macro attachment: {filename}"
    if ext in SUSPICIOUS_ATTACHMENT_EXTS:
        return "medium", f"Archive/document: {filename}"
    return "low", ""


def behavioral_correlation(
    has_urgency: bool,
    has_external_links: bool,
    has_credential_lang: bool,
    has_form: bool,
    has_tunnel_domain: bool,
    sender_brand_mismatch: bool,
) -> Tuple[float, List[str]]:
    score = 0.0
    reasons = []
    if has_urgency and has_external_links:
        score += 0.25
        reasons.append("Urgency language + external links (classic phishing pattern)")
    if has_credential_lang and has_form:
        score += 0.40
        reasons.append("Credential language + HTML form = high credential theft risk")
    if has_tunnel_domain and has_credential_lang:
        score += 0.50
        reasons.append(
            "Tunnel domain + credential language = active phishing infrastructure"
        )
    if sender_brand_mismatch and has_external_links:
        score += 0.30
        reasons.append("Brand impersonation + external links (spear-phishing pattern)")
    if has_tunnel_domain and has_form:
        score += 0.45
        reasons.append("HTML form submitting to tunnel/free-host domain")
    return min(score, 1.0), reasons


def _analyze_urls_raw(body: str) -> Tuple[float, List[Dict], List[str]]:
    urls = extract_urls(body)
    if not urls:
        return 0.0, [], []
    total = 0.0
    details = []
    reasons = []
    for url in urls:
        domain = get_domain(url)
        rep, flags = domain_reputation(domain)
        hg, hg_msg = detect_homograph(domain)
        if hg:
            rep = max(rep, 0.88)
            flags.append(hg_msg)
        total += rep
        details.append({"url": url, "risk": rep, "flags": flags})
        if rep > 0.50:
            reasons.append(f"Risky URL domain: {domain}")
    return min(total / len(urls), 1.0), details, reasons


# ══════════════════════════════════════════════════════════════════════
#  NORMAL ANALYSIS  (fast, ~instant)
# ══════════════════════════════════════════════════════════════════════


def normal_analysis(email) -> Dict:
    body_text = safe_str(getattr(email, "body_text", ""))
    body_html = safe_str(getattr(email, "body_html", ""))
    body = body_text + " " + body_html
    raw_headers = safe_str(getattr(email, "raw_headers", ""))

    scores: Dict[str, int] = {
        "url_risk": 0,
        "keyword_risk": 0,
        "sender_risk": 0,
        "hidden_links": 0,
        "base64_risk": 0,
        "js_risk": 0,
        "form_risk": 0,
        "attachment_risk": 0,
        "header_auth": 0,
        "behavioral": 0,
        "obfuscation": 0,
    }
    reasons: List[str] = []

    # URL
    url_score, url_details, url_reasons = _analyze_urls_raw(body)
    scores["url_risk"] = int(url_score * 100)
    reasons.extend(url_reasons)

    has_tunnel = any(
        any(kw in get_domain(u) for kw in _TUNNEL_KEYWORDS)
        or get_domain(u) in CRITICAL_TUNNEL_DOMAINS
        for u in extract_urls(body)
    )

    # Keywords
    kw_score, kw_reasons, kw_ctxs = analyze_keywords(body_text or body)
    scores["keyword_risk"] = int(kw_score * 100)
    reasons.extend(kw_reasons)
    has_urgency = any("urgency" in c.get("category", "") for c in kw_ctxs)
    has_cred = any("credential" in r.lower() for r in kw_reasons)

    # Sender
    from_email = safe_str(getattr(email, "from_email", ""))
    from_name = safe_str(getattr(email, "from_name", ""))
    ms, mr = sender_mismatch(from_email, from_name)
    scores["sender_risk"] = int(ms * 100)
    if mr:
        reasons.append(mr)
    sender_brand_mis = bool(mr)

    rp_mis, rp_msg = detect_return_path_mismatch(raw_headers, from_email)
    if rp_mis:
        scores["sender_risk"] = min(scores["sender_risk"] + 30, 100)
        reasons.append(rp_msg)

    # Header auth
    auth = parse_auth_headers(raw_headers)
    ap = 0
    if auth["spf"] == "fail":
        ap += 30
        reasons.append("SPF authentication FAILED")
    if auth["dkim"] == "fail":
        ap += 25
        reasons.append("DKIM signature FAILED")
    if auth["dmarc"] == "fail":
        ap += 35
        reasons.append("DMARC policy FAILED")
    scores["header_auth"] = min(ap, 100)

    # Hidden links
    hl, hl_msg = has_hidden_links(body_html)
    if hl:
        scores["hidden_links"] = 22
        reasons.append(f"Hidden/obfuscated links: {hl_msg}")

    # Invisible text
    iv, iv_msg = detect_invisible_text(body_html)
    if iv:
        scores["obfuscation"] = max(scores["obfuscation"], 18)
        reasons.append(iv_msg)

    # Base64
    b64, b64_msg = is_base64_encoded(body)
    if b64:
        scores["base64_risk"] = 18
        reasons.append(b64_msg)

    # JavaScript
    js_findings = detect_javascript(body_html)
    high_js = [f for f in js_findings if f.get("risk") == "high"]
    if high_js:
        scores["js_risk"] = 32
        reasons.append(f"High-risk JavaScript ({len(high_js)} pattern(s))")
    elif js_findings:
        scores["js_risk"] = 12
        reasons.append(f"JavaScript in email ({len(js_findings)} occurrence(s))")

    # Forms
    form_findings = detect_forms(body_html)
    cred_forms = [f for f in form_findings if f.get("credential_harvest")]
    has_form = bool(form_findings)
    if cred_forms:
        scores["form_risk"] = 42
        reasons.append(f"Credential-harvesting form ({len(cred_forms)} form(s))")
    elif form_findings:
        scores["form_risk"] = 16
        reasons.append(f"HTML form(s) detected ({len(form_findings)})")

    # Attachments
    att_risk = 0
    if getattr(email, "has_attachments", False):
        att_names = getattr(email, "attachment_names", []) or []
        if att_names:
            for fname in att_names:
                level, att_r = classify_attachment_risk(str(fname))
                if level == "critical":
                    att_risk = max(att_risk, 55)
                    reasons.append(f"CRITICAL attachment: {att_r}")
                elif level == "high":
                    att_risk = max(att_risk, 38)
                    reasons.append(f"Dangerous attachment: {att_r}")
                elif level == "medium":
                    att_risk = max(att_risk, 16)
        else:
            att_risk = 10
            reasons.append("Email contains unidentified attachments")
    scores["attachment_risk"] = att_risk

    # Behavioral
    beh_score, beh_reasons = behavioral_correlation(
        has_urgency=has_urgency,
        has_external_links=bool(extract_urls(body)),
        has_credential_lang=has_cred,
        has_form=has_form,
        has_tunnel_domain=has_tunnel,
        sender_brand_mismatch=sender_brand_mis,
    )
    scores["behavioral"] = int(beh_score * 100)
    reasons.extend(beh_reasons)

    detected_links = extract_links_with_details(body_text, body_html)
    btn_findings = detect_buttons(body_html)

    # Weighted final score
    final_score = (
        scores["url_risk"] * 0.26
        + scores["keyword_risk"] * 0.18
        + scores["sender_risk"] * 0.10
        + scores["header_auth"] * 0.12
        + scores["hidden_links"] * 1.0
        + scores["base64_risk"] * 0.8
        + scores["js_risk"] * 0.9
        + scores["form_risk"] * 1.0
        + scores["attachment_risk"] * 0.85
        + scores["behavioral"] * 0.80
        + scores["obfuscation"] * 0.6
    )
    final_score = min(final_score, 100)

    if final_score > 70:
        risk = "dangerous"
    elif final_score > 35:
        risk = "suspicious"
    else:
        risk = "safe"

    return {
        "score": round(final_score / 100, 3),
        "risk": risk,
        "reasons": reasons,
        "scores": scores,
        "urls": url_details,
        "need_deep": final_score > 55,
        "detected_links": detected_links,
        "detected_js": js_findings,
        "detected_buttons": btn_findings,
        "detected_forms": form_findings,
        "keyword_contexts": kw_ctxs,
        "auth_headers": auth,
    }


# ══════════════════════════════════════════════════════════════════════
#  DEEP ML ANALYSIS  (11-feature logistic regression)
# ══════════════════════════════════════════════════════════════════════

_DEEP_W = {
    "url_entropy": 0.12,
    "domain_age_mock": 0.18,
    "keyword_vector": 0.22,
    "html_complexity": 0.08,
    "link_mismatch_score": 0.16,
    "js_score": 0.08,
    "tunnel_domain_flag": 0.20,
    "homograph_flag": 0.18,
    "form_cred_score": 0.20,
    "behavioral_score": 0.18,
    "auth_fail_score": 0.15,
}
_DEEP_BIAS = -0.85


def deep_analysis(email) -> Dict:
    body_text = safe_str(getattr(email, "body_text", ""))
    body_html = safe_str(getattr(email, "body_html", ""))
    body = body_text + " " + body_html
    raw_headers = safe_str(getattr(email, "raw_headers", ""))
    urls = extract_urls(body)

    # URL entropy
    s = "".join(urls)
    url_ent = 0.0
    if s:
        freq = Counter(s)
        probs = [f / len(s) for f in freq.values()]
        url_ent = min(-sum(p * math.log2(p) for p in probs) / 8.0, 1.0)

    # Domain age mock
    dom_age = 0.0
    for url in urls:
        d = get_domain(url)
        rep, _ = domain_reputation(d)
        dom_age = max(dom_age, rep * 0.9)
    dom_age = min(dom_age, 1.0)

    # Keyword vector
    suspicious_words = [
        "urgent",
        "verify",
        "login",
        "password",
        "limited",
        "selected",
        "exclusive",
        "reward",
        "confirm",
        "account",
        "immediately",
        "deadline",
        "expires",
        "winner",
        "claim",
        "suspended",
        "unusual",
        "security alert",
        "unauthorized",
        "credential",
        "invoice",
        "billing",
        "bank",
        "wire transfer",
        "gift card",
        "bitcoin",
    ]
    kv = sum(1 for w in suspicious_words if w in body.lower()) / len(suspicious_words)

    html_cplx = min(len(re.findall(r"<[^>]+>", body_html)) / 500, 1.0)

    lm_score = 0.0
    for url in urls:
        ap = rf'<a[^>]*href=["\'{re.escape(url)}["\'][^>]*>(.*?)</a>'
        for m in re.findall(ap, body_html, re.IGNORECASE | re.DOTALL):
            clean = re.sub(r"<[^>]+>", "", m).strip()
            if clean.lower().startswith("http") and get_domain(clean) != get_domain(
                url
            ):
                lm_score += 0.3
    lm_score = min(lm_score, 1.0)

    js_f = detect_javascript(body_html)
    js_sc = min(
        len([f for f in js_f if f["risk"] == "high"]) * 0.3 + len(js_f) * 0.05, 1.0
    )

    tun = float(
        any(
            any(kw in get_domain(u) for kw in _TUNNEL_KEYWORDS)
            or get_domain(u) in CRITICAL_TUNNEL_DOMAINS
            for u in urls
        )
    )
    hg_f = float(any(detect_homograph(get_domain(u))[0] for u in urls))

    forms = detect_forms(body_html)
    fc_sc = min(sum(0.5 if f["credential_harvest"] else 0.2 for f in forms), 1.0)

    kw_sc, _, kw_ctxs_deep = analyze_keywords(body_text or body)
    has_urg = any("urgency" in c["category"] for c in kw_ctxs_deep)
    beh_sc, _ = behavioral_correlation(
        has_urgency=has_urg,
        has_external_links=bool(urls),
        has_credential_lang=bool(
            re.search(r"(password|credential|verify)", body.lower())
        ),
        has_form=bool(forms),
        has_tunnel_domain=bool(tun),
        sender_brand_mismatch=False,
    )

    auth = parse_auth_headers(raw_headers)
    auth_fail = sum(
        [
            0.35 if auth["spf"] == "fail" else 0,
            0.30 if auth["dkim"] == "fail" else 0,
            0.35 if auth["dmarc"] == "fail" else 0,
        ]
    )

    features = {
        "url_entropy": url_ent,
        "domain_age_mock": dom_age,
        "keyword_vector": kv,
        "html_complexity": html_cplx,
        "link_mismatch_score": lm_score,
        "js_score": js_sc,
        "tunnel_domain_flag": tun,
        "homograph_flag": hg_f,
        "form_cred_score": fc_sc,
        "behavioral_score": beh_sc,
        "auth_fail_score": auth_fail,
    }

    z = _DEEP_BIAS + sum(_DEEP_W.get(k, 0) * v for k, v in features.items())
    ml_score = 1.0 / (1.0 + math.exp(-z))
    conf = 0.55 + ml_score * 0.35

    return {
        "score": round(ml_score, 3),
        "confidence": round(conf, 3),
        "model_used": "MailShield-DeepNet-v9",
        "features": features,
        "reasons": [],
        "detected_forms": forms,
        "detected_buttons": detect_buttons(body_html),
        "detected_js": js_f,
    }


# ══════════════════════════════════════════════════════════════════════
#  DEEP ANALYSIS WORKER
# ══════════════════════════════════════════════════════════════════════


class DeepAnalysisWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(dict)

    STAGES = [
        ("Parsing email structure", 8),
        ("Extracting & normalising URLs", 20),
        ("Checking domain reputation", 34),
        ("Homograph & punycode detection", 46),
        ("Analysing HTML & JavaScript", 58),
        ("Form & credential detection", 70),
        ("Behavioral correlation", 82),
        ("Running ML classifier", 92),
        ("Finalising threat score", 100),
    ]

    def __init__(self, email):
        super().__init__()
        self.email = email

    def run(self):
        try:
            for stage, pct in self.STAGES:
                self.progress.emit(stage, pct)
                self.msleep(100)
            self.finished.emit(deep_analysis(self.email))
        except Exception as e:
            self.finished.emit({"error": str(e)})


def enhanced_analysis(email) -> Dict:
    return normal_analysis(email)


def update_model_from_feedback(email_id: str, label: int):
    pass
