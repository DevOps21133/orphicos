#!/bin/bash
set -euo pipefail
mkdir -p /opt/orphicos /var/lib/orphicos
install -m 755 /tmp/anfrage.py /opt/orphicos/anfrage.py
install -m 644 /tmp/orphicos-anfrage.service /etc/systemd/system/orphicos-anfrage.service
chown -R www-data:www-data /var/lib/orphicos
chmod 750 /var/lib/orphicos

python3 << 'PY'
from pathlib import Path

sec = Path("/etc/nginx/snippets/orphicos-security.conf")
t = sec.read_text()
old_if = "if ($request_method !~ ^(GET|HEAD)$) { return 405; }"
if old_if in t:
    t = t.replace(old_if, "# POST allowed only at location = /api/anfrage (see site conf).")
t = t.replace("form-action 'none'", "form-action 'self'")
sec.write_text(t)

loc = """
    location = /api/anfrage {
        limit_except POST GET { deny all; }
        proxy_pass http://127.0.0.1:8099/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 20s;
    }
"""

candidates = [
    Path("/etc/nginx/sites-available/orphicos.app.conf"),
    Path("/etc/nginx/sites-enabled/orphicos.app.conf"),
]
seen = set()
for p in candidates:
    if not p.exists():
        continue
    real = p.resolve()
    if real in seen:
        continue
    seen.add(real)
    s = p.read_text()
    if "location = /api/anfrage" not in s:
        needle = "    location /download/"
        if needle not in s:
            raise SystemExit(f"download location not found in {p}")
        s = s.replace(needle, loc + "\n" + needle)
    old = "    location / {\n        try_files $uri $uri/ =404;\n    }"
    new = "    location / {\n        limit_except GET HEAD { deny all; }\n        try_files $uri $uri/ =404;\n    }"
    if old in s and "limit_except GET HEAD" not in s:
        s = s.replace(old, new)
    p.write_text(s)
    print("patched", p)
PY

nginx -t
systemctl daemon-reload
systemctl enable --now orphicos-anfrage.service
systemctl reload nginx
systemctl --no-pager --full status orphicos-anfrage.service | sed -n '1,18p'
curl -sS http://127.0.0.1:8099/health
echo
