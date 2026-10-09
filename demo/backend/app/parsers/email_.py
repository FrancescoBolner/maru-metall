"""E-mails (.eml and Outlook .msg): headers, plain-text body, attachments."""
from __future__ import annotations

import email
import re
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Optional


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def _clean_body(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"<https?://[^>]{60,}>", "<link>", text)
    return text.strip()


def parse_eml(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    msg = email.message_from_bytes(raw, policy=policy.default)
    body = ""
    html = ""
    attachments = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        fname = part.get_filename()
        disp = (part.get("Content-Disposition") or "").lower()
        cid = (part.get("Content-ID") or "").strip("<>")
        if fname or "attachment" in disp:
            data = part.get_payload(decode=True) or b""
            attachments.append({"name": fname or f"attachment-{len(attachments) + 1}", "content_type": ctype,
                                "data": data, "inline": "inline" in disp or bool(cid), "cid": cid})
        elif ctype == "text/plain" and not body:
            try:
                body = part.get_content()
            except Exception:
                body = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        elif ctype == "text/html" and not html:
            try:
                html = part.get_content()
            except Exception:
                html = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
    if not body and html:
        body = _html_to_text(html)
    date = None
    try:
        date = parsedate_to_datetime(msg["Date"]).isoformat() if msg["Date"] else None
    except Exception:
        date = None
    return {
        "from": str(msg["From"] or ""), "to": str(msg["To"] or ""), "cc": str(msg["Cc"] or ""),
        "subject": str(msg["Subject"] or ""), "date": date, "body": _clean_body(body),
        "attachments": attachments,
    }


def parse_msg(path: Path) -> dict[str, Any]:
    import extract_msg

    m = extract_msg.openMsg(str(path))
    try:
        body = m.body or ""
        if not body and getattr(m, "htmlBody", None):
            hb = m.htmlBody
            body = _html_to_text(hb.decode("utf-8", errors="replace") if isinstance(hb, bytes) else hb)
        date = None
        try:
            d = m.date
            date = d.isoformat() if isinstance(d, datetime) else (str(d) if d else None)
        except Exception:
            date = None
        attachments = []
        for a in m.attachments:
            data = getattr(a, "data", None)
            if isinstance(data, (bytes, bytearray)):
                attachments.append({"name": a.longFilename or a.shortFilename or f"attachment-{len(attachments) + 1}",
                                    "content_type": getattr(a, "mimetype", None) or "application/octet-stream",
                                    "data": bytes(data), "inline": bool(getattr(a, "contentId", None)),
                                    "cid": getattr(a, "contentId", None) or ""})
        return {"from": str(m.sender or ""), "to": str(m.to or ""), "cc": str(m.cc or ""),
                "subject": str(m.subject or ""), "date": date, "body": _clean_body(body), "attachments": attachments}
    finally:
        try:
            m.close()
        except Exception:
            pass


def parse(path: Path) -> dict[str, Any]:
    return parse_msg(path) if Path(path).suffix.lower() == ".msg" else parse_eml(path)


def split_thread(body: str) -> list[dict[str, Any]]:
    """Split a reply chain into messages (newest first) at 'From:/Fra:/Saatja:' header blocks."""
    marks = [m.start() for m in re.finditer(r"(?m)^(?:From|Fra|Från|Saatja|Lähettäjä):\s", body)]
    if not marks:
        return [{"text": body, "offset": 0}]
    parts = []
    starts = [0] + marks
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(body)
        chunk = body[s:e].strip()
        if chunk:
            parts.append({"text": chunk, "offset": s})
    return parts


def body_offset(body: str, snippet: str) -> Optional[int]:
    if not snippet:
        return None
    i = body.find(snippet)
    if i >= 0:
        return i
    norm = re.sub(r"\s+", " ", body)
    j = norm.find(re.sub(r"\s+", " ", snippet))
    return j if j >= 0 else None
