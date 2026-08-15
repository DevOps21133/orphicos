#!/usr/bin/env python3
"""Local lead intake for orphicos.app. Binds 127.0.0.1 only. Nginx proxies POST /api/anfrage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HOST = os.environ.get("ORPHICOS_ANFRAGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ORPHICOS_ANFRAGE_PORT", "8099"))
DB_PATH = os.environ.get("ORPHICOS_ANFRAGE_DB", "/var/lib/orphicos/leads.db")
MAIL_TO = os.environ.get("ORPHICOS_ANFRAGE_TO", "bloimlala@gmail.com")
MAIL_FROM = os.environ.get("ORPHICOS_ANFRAGE_FROM", "anfrage@orphicos.app")
SENDMAIL = os.environ.get("ORPHICOS_SENDMAIL", "/usr/sbin/sendmail")
MAX_BODY = 12_000
PER_IP_HOUR = 6
GLOBAL_HOUR = 40

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[+\d][\d\s/().-]{5,24}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT NOT NULL,
  company TEXT NOT NULL,
  role TEXT,
  industry TEXT,
  employees TEXT,
  message TEXT,
  ip TEXT,
  user_agent TEXT
);
"""

_hits: list[tuple[str, float]] = []


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(SCHEMA)
    return con


def prune_hits(now: float) -> None:
    cutoff = now - 3600
    while _hits and _hits[0][1] < cutoff:
        _hits.pop(0)


def rate_ok(ip: str) -> bool:
    now = time.time()
    prune_hits(now)
    if sum(1 for _, t in _hits if now - t < 3600) >= GLOBAL_HOUR:
        return False
    if sum(1 for a, t in _hits if a == ip and now - t < 3600) >= PER_IP_HOUR:
        return False
    _hits.append((ip, now))
    return True


def clean(val, n: int) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        val = val[0] if val else ""
    s = str(val).replace("\x00", "").strip()
    s = re.sub(r"[\r\n]+", " ", s)
    return s[:n]


def parse_body(raw: bytes, ctype: str) -> dict:
    text = raw.decode("utf-8", errors="replace")
    if "application/json" in ctype:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    return {k: (v[-1] if v else "") for k, v in parse_qs(text, keep_blank_values=True).items()}


def validate(data: dict) -> tuple[dict | None, str | None]:
    if clean(data.get("website") or data.get("url") or data.get("hp"), 80):
        return None, "honeypot"
    out = {
        "name": clean(data.get("name"), 80),
        "phone": clean(data.get("phone"), 32),
        "email": clean(data.get("email"), 120).lower(),
        "company": clean(data.get("company"), 120),
        "role": clean(data.get("role"), 80),
        "industry": clean(data.get("industry"), 80),
        "employees": clean(data.get("employees"), 40),
        "message": clean(data.get("message"), 2000),
    }
    if not out["name"] or len(out["name"]) < 2:
        return None, "Bitte einen Namen angeben."
    if not PHONE_RE.match(out["phone"]):
        return None, "Bitte eine gültige Telefonnummer angeben."
    if not EMAIL_RE.match(out["email"]):
        return None, "Bitte eine gültige E-Mail-Adresse angeben."
    if not out["company"] or len(out["company"]) < 2:
        return None, "Bitte das Unternehmen angeben."
    if not data.get("consent"):
        return None, "Bitte die Einwilligung bestätigen."
    return out, None


def store(row: dict, ip: str, ua: str) -> int:
    con = db()
    try:
        cur = con.execute(
            """INSERT INTO leads
               (created_at, name, phone, email, company, role, industry, employees, message, ip, user_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                row["name"],
                row["phone"],
                row["email"],
                row["company"],
                row["role"],
                row["industry"],
                row["employees"],
                row["message"],
                ip[:64],
                ua[:240],
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def mail_bytes(row: dict, lead_id: int, ip: str) -> bytes:
    body = (
        f"Neue Erstgespräch-Anfrage #{lead_id}\n"
        f"https://orphicos.app\n\n"
        f"Name:         {row['name']}\n"
        f"Telefon:      {row['phone']}\n"
        f"E-Mail:       {row['email']}\n"
        f"Unternehmen:  {row['company']}\n"
        f"Funktion:     {row['role'] or '—'}\n"
        f"Branche:      {row['industry'] or '—'}\n"
        f"Mitarbeiter:  {row['employees'] or '—'}\n\n"
        f"Nachricht:\n{row['message'] or '—'}\n\n"
        f"IP: {ip}\n"
        "Rufen Sie an. Die Person erwartet einen Rückruf.\n"
    )
    msg = (
        f"From: OrphicOS Anfrage <{MAIL_FROM}>\n"
        f"To: {MAIL_TO}\n"
        f"Subject: Neue Anfrage: {row['company']} / {row['name']}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"\n{body}"
    )
    return msg.encode("utf-8")


def notify(row: dict, lead_id: int, ip: str) -> None:
    raw = mail_bytes(row, lead_id, ip)
    outbox = os.path.join(os.path.dirname(DB_PATH), "outbox")
    os.makedirs(outbox, exist_ok=True)
    path = os.path.join(outbox, f"lead-{lead_id}.eml")
    with open(path, "wb") as fh:
        fh.write(raw)
    subprocess.run(
        [SENDMAIL, "-t", "-oi", "-f", MAIL_FROM],
        input=raw,
        check=True,
        timeout=20,
    )
    try:
        os.remove(path)
    except OSError:
        pass


OK_HTML = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anfrage erhalten</title>
<link rel="stylesheet" href="/styles.css"></head>
<body><main class="wrap" style="padding:80px 20px">
<h1>Wir werden Sie umgehend kontaktieren.</h1>
<p>Ihre Angaben sind angekommen. Wir rufen Sie zurück.</p>
<p><a href="/de/">Zurück zur Startseite</a></p>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "orphicos-anfrage/1"

    def log_message(self, fmt, *args):
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _origin_ok(self) -> bool:
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if not origin:
            return True
        return origin in {"https://orphicos.app", "https://www.orphicos.app"}

    def _ip(self) -> str:
        xff = self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For") or ""
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0]

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in {"", "/health"}:
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._origin_ok():
            self._send(403, json.dumps({"ok": False, "error": "forbidden"}).encode(), "application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(413, json.dumps({"ok": False, "error": "Anfrage zu groß."}).encode(), "application/json")
            return
        raw = self.rfile.read(length)
        ip = self._ip()
        wants_html = "text/html" in (self.headers.get("Accept") or "") and "application/json" not in (
            self.headers.get("Accept") or ""
        )
        try:
            data = parse_body(raw, self.headers.get("Content-Type") or "")
        except Exception:
            self._send(400, json.dumps({"ok": False, "error": "Ungültige Anfrage."}).encode(), "application/json")
            return
        if not rate_ok(ip):
            err = "Bitte etwas warten und es erneut versuchen."
            if wants_html:
                self._send(429, f"<p>{err}</p>".encode(), "text/html; charset=utf-8")
            else:
                self._send(429, json.dumps({"ok": False, "error": err}).encode(), "application/json")
            return
        row, err = validate(data)
        if err == "honeypot":
            if wants_html:
                self._send(200, OK_HTML.encode(), "text/html; charset=utf-8")
            else:
                self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            return
        if err:
            if wants_html:
                self._send(400, f"<p>{err}</p>".encode(), "text/html; charset=utf-8")
            else:
                self._send(400, json.dumps({"ok": False, "error": err}).encode(), "application/json")
            return
        lead_id = store(row, ip, self.headers.get("User-Agent") or "")
        try:
            notify(row, lead_id, ip)
        except Exception as exc:
            __import__("sys").stderr.write("mail failed lead %s: %s\n" % (lead_id, exc))
        if wants_html:
            self._send(200, OK_HTML.encode(), "text/html; charset=utf-8")
        else:
            self._send(200, json.dumps({"ok": True, "id": lead_id}).encode(), "application/json")


def main():
    db().close()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
