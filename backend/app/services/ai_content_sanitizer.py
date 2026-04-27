"""
Redact PII and secrets from user-facing text before sending to external LLM APIs.

Best-effort regex: not a full DLP; expect false positives and some misses.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Match

# --- Placeholders (short, consistent) ---
P_URL = "[REDACTED:url]"
P_EMAIL = "[REDACTED:email]"
P_IP = "[REDACTED:ip]"
P_MAC = "[REDACTED:mac]"
P_HOST = "[REDACTED:host]"
P_PHONE = "[REDACTED:phone]"
P_JWT = "[REDACTED:token]"
P_PEOPLE = "[REDACTED:person]"
P_DOC = "[REDACTED:id]"

_RE_URL = re.compile(
    r"""(?ix)
    \b
    (?:https?|socks5h?|sftp|ftps?|wss?|rediss?)
    ://
    (?:[\w$_.+!*'(),;?&=-]+(?::[^@\s/]*)?@)?  # userinfo@ optional
    (?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)*
    [a-z0-9](?:[a-z0-9-]*[a-z0-9])?
    (?:[/#?][^\s<>"'{}\\|`^\[\]]*)?
    """,
    re.VERBOSE,
)
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}\b"
)

# IPv4 (dotted quads; validate with ipaddress)
_RE_IPV4 = re.compile(
    r"""
    (?<![0-9.])
    (?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])
    (?:\.
    (?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])
    ){3}
    (?![0-9.])
    """,
    re.VERBOSE,
)

# IPv6: rough candidates, validate with ipaddress.IPv6Address
_RE_IPV6_CAND = re.compile(
    r"(?i)(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){1,7}[0-9A-Fa-f]{0,4}"
    r"|::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{0,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,6}::"
    r"|:(?::[0-9A-Fa-f]{1,4}){1,6}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5})"
    r"(?![0-9A-Fa-f.:])"
)

_RE_MAC = re.compile(
    r"(?i)(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:.-])"
)

# At least 2 labels, final label looks like a TLD; skip single-letter TLDs
_RE_FQDN = re.compile(
    r"""(?ix)
    (?<![0-9A-Z._/%-])
    \b
    (?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+
    (?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})
    (?![a-z0-9.-])
    """
)

# RU: +7 / 7 / 8 and 10 digits; international +country (not 7) and 5–16 digits
_RE_RU_PHONE = re.compile(
    r"""(?x)
    (?<!\d)
    (?:
      (?:\+7|7|8)(?:[ \-()]*)?\(?[489][0-9]{2}\)?(?:[ \-]*[0-9]){3}(?:[ \-]*[0-9]{2}){2}
    | \+(?!7)(?:[1-9][0-9]{0,2})[0-9 \-()]{3,20}\d
    )
    (?!\d)
    """
)

_RE_PASSPORT = re.compile(r"\b\d{4}[\s-]+\d{6}\b")

# Block of 11+ consecutive digits (INN, SNILS, long cards without spaces, etc.)
_RE_LONG_DID = re.compile(r"(?<![0-9])\d{11,20}(?![0-9])")

_RE_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_+\-=/]{10,}\.[A-Za-z0-9_+\-=/]{10,}\.[A-Za-z0-9_+\-=./]{10,}\b"
)

# Russian: Фамилия Имя + отчество (окончания отчества)
_RE_RU_PATRONYM = re.compile(
    r"""
    [А-ЯЁ][а-яё]{1,30}
    \s+
    [А-ЯЁ][а-яё]{1,30}
    \s+
    [А-ЯЁ][а-яё]+
    (?:овна|овны|ович|евна|евич|ьич|йич|кызы|кизи|оглы)
    (?=[\s.,;:!?)»'\"]|$)
    """,
    re.VERBOSE,
)


def _try_ipv4_repl(m: Match[str]) -> str:
    s = m.group(0)
    try:
        ipaddress.IPv4Address(s)
    except ValueError:
        return s
    return P_IP


def _try_ipv6_repl(m: Match[str]) -> str:
    s = m.group(0).strip()
    t = s.split("%", 1)[0].split("/", 1)[0]
    try:
        ipaddress.IPv6Address(t)
    except ValueError:
        return m.group(0)
    return P_IP


def _redact_fqdn_one(m: Match[str]) -> str:
    raw = m.group(0)
    low = raw.lower()
    if low in {"e.g", "i.e", "a.m", "p.m"}:
        return raw
    parts = low.split(".")
    if not parts or all(p.isdigit() for p in parts if p not in ("")):
        return raw
    if len(parts) == 2 and len(parts[1]) <= 1:
        return raw
    return P_HOST


def redact_for_llm(text: str) -> str:
    """
    Redact common sensitive patterns from text sent to third-party model APIs.

    Order: URLs and emails first, then IPs, then hostnames, phones, id numbers, FIO.
    """
    if not text:
        return text

    t = str(text)
    t = _RE_URL.sub(P_URL, t)
    t = _RE_EMAIL.sub(P_EMAIL, t)
    t = _RE_IPV4.sub(_try_ipv4_repl, t)
    t = _RE_IPV6_CAND.sub(_try_ipv6_repl, t)
    t = _RE_MAC.sub(P_MAC, t)
    t = _RE_JWT.sub(P_JWT, t)
    t = _RE_FQDN.sub(_redact_fqdn_one, t)
    t = _RE_RU_PHONE.sub(P_PHONE, t)
    t = _RE_PASSPORT.sub(P_DOC, t)
    t = _RE_LONG_DID.sub(P_DOC, t)
    t = _RE_RU_PATRONYM.sub(P_PEOPLE, t)
    return t
