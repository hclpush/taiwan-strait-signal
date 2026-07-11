#!/usr/bin/env python3
"""Email alerts — level changes and pipeline failures.

Backends, tried in order:
  1. ZSend (Zeabur email API) if ops/zsend.env provides ZSEND_API_KEY
     (file format: KEY=value lines; see ops/README)
  2. macOS Mail.app via osascript (requires Mail configured on this Mac)

Every send failure raises — run-weekly.sh surfaces it in the log + notification.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TO = "ycbxvn@gmail.com"
ZSEND_ENV = ROOT / "ops" / "zsend.env"
ZSEND_URL = "https://zsend.zeabur.com/api/v1/mail"

LEVEL_NAMES = {1: "1 平時 Calm", 2: "2 留意 Elevated", 3: "3 警戒 Serious",
               4: "4 高度警戒 Critical", 5: "5 撤離 Imminent"}


def _zsend_conf() -> dict | None:
    if not ZSEND_ENV.exists():
        return None
    conf = {}
    for line in ZSEND_ENV.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf if conf.get("ZSEND_API_KEY") else None


def _send_zsend(conf: dict, subject: str, body: str) -> None:
    payload = {
        "from": conf.get("ZSEND_FROM", "strait-signal@zeabur.app"),
        "to": [TO],
        "subject": subject,
        "text": body,
    }
    req = urllib.request.Request(
        conf.get("ZSEND_URL", ZSEND_URL),
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {conf['ZSEND_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"zsend HTTP {resp.status}")


def _send_mailapp(subject: str, body: str) -> None:
    # Body/subject passed as argv — never interpolated into the script source —
    # so message content cannot inject AppleScript.
    script = (
        'on run argv\n'
        'tell application "Mail"\n'
        "  set m to make new outgoing message with properties "
        "{subject:(item 1 of argv), content:(item 2 of argv), visible:false}\n"
        '  tell m to make new to recipient with properties {address:(item 3 of argv)}\n'
        "  send m\n"
        "end tell\n"
        "end run"
    )
    subprocess.run(
        ["/usr/bin/osascript", "-e", script, subject, body, TO],
        check=True, capture_output=True, text=True, timeout=60,
    )


def send(subject: str, body: str) -> None:
    conf = _zsend_conf()
    if conf:
        _send_zsend(conf, subject, body)
    else:
        _send_mailapp(subject, body)
    print(f"email sent: {subject}")


def level_change_message(old: int, new: int, changes: dict, meta: dict) -> tuple[str, str]:
    """Title + body for a level-change alert — emailed locally, or written to
    runs/<date>/level-change.json for CI to open a GitHub Issue from."""
    arrow = "升級 ↑" if new > old else "降級 ↓"
    lines = [
        f"台海燈號 {arrow}  {LEVEL_NAMES[old]}  →  {LEVEL_NAMES[new]}",
        "",
        "本次變更 Changes:",
    ]
    for k, v in changes.items():
        lines.append(f"  {k}: {v['from']} → {v['to']}  {v['note_zh']}")
    url = meta.get("deploy_url") or "(not deployed yet)"
    lines += [
        "",
        f"網站 Site: {url}",
        "回滾 Rollback: python3 pipeline/apply.py --rollback（本地執行，然後 git push）",
        "",
        "此通知由 strait-signal 每週管線自動發出。",
    ]
    return f"[台海燈號] Level {old} → {new}", "\n".join(lines)


def send_level_change(old: int, new: int, changes: dict, meta: dict) -> None:
    subject, body = level_change_message(old, new, changes, meta)
    send(subject, body)


def send_failure(consecutive: int, detail: str) -> None:
    send(
        f"[台海燈號] pipeline failed {consecutive}x",
        f"The weekly strait-signal run has failed {consecutive} times in a row.\n\n"
        f"Last error:\n{detail[:2000]}\n\n"
        f"Site keeps its last published state (最後審視 date shows staleness).\n"
        f"Logs: ~/.claude/logs/strait-signal.log",
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="send a test email")
    ap.add_argument("--failure", type=int, metavar="N", help="send failure alert")
    ap.add_argument("--detail", default="", help="failure detail text")
    args = ap.parse_args()
    if args.test:
        send("[台海燈號] test alert", "Email path works. 電子郵件通知測試成功。")
    elif args.failure:
        send_failure(args.failure, args.detail)
