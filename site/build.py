#!/usr/bin/env python3
"""Build site/dist/index.html from data/*.json + site/template.html.

Pure stdlib. Every dynamic string is HTML-escaped so nothing the pipeline
writes into data/ can inject markup into the public page. The signal level
is computed by pipeline/levels.py — never stored, never trusted from data.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from levels import compute_level, counts  # noqa: E402

LEVEL_HEX = {1: "0ca30c", 2: "fab219", 3: "ec835a", 4: "d03b3b", 5: "6d28d9"}
PIP_CLASS = {0: "", 1: " half", 2: " full"}

# Hand-drawn ellipse variants for the red-circle (clipping) motif.
CIRCLE_PATHS = [
    "M9,21 C5,8 28,2 51,3 C77,4 95,8 94,19 C93,31 71,38 45,37 C21,36 10,32 9,23",
    "M8,19 C7,7 31,1 53,3 C78,5 96,10 94,21 C92,32 69,38 44,36 C20,34 9,30 8,21",
    "M10,20 C7,9 29,3 50,3 C76,3 94,9 93,20 C92,31 70,37 46,36 C22,35 11,31 10,22",
    "M8,20 C6,8 30,2 52,3 C77,4 95,9 94,20 C93,32 68,38 44,37 C21,36 9,31 8,22",
]
WAR_CIRCLE_PATH = (
    "M8,20 C5,7 29,1 52,2 C78,3 96,8 95,20 C94,33 69,39 44,38 "
    "C20,37 9,32 8,22 C7,12 20,5 38,4"
)


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def zh_en(zh: str, en: str) -> str:
    return f'<span class="zh">{esc(zh)}</span><span class="en">{esc(en)}</span>'


def safe_url(u: str) -> str:
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return "#"
    return esc(u)


def circled(text: str, path: str) -> str:
    return (
        f'<span class="circled">{esc(text)}'
        f'<svg viewBox="0 0 100 40" preserveAspectRatio="none">'
        f'<path d="{path}"/></svg></span>'
    )


def build() -> Path:
    data = {
        name: json.loads((ROOT / "data" / f"{name}.json").read_text())
        for name in ("indicators", "timeline", "levels", "meta")
    }
    inds = data["indicators"]["indicators"]
    cats = data["indicators"]["categories"]
    levels = data["levels"]["levels"]
    meta = data["meta"]

    n = compute_level(inds)
    c = counts(inds)
    cur = levels[n - 1]
    assert cur["n"] == n
    date = meta["lastReviewed"].replace("-", "/")

    # --- meter ---
    segs = []
    for lv in levels:
        i = lv["n"]
        var = lv["color"] if i <= n else lv["track"]
        cls = "seg cur" if i == n else "seg"
        segs.append(f'      <div class="{cls}" style="background:var({var})"></div>')
    labels = []
    for lv in levels:
        active = ' class="active"' if lv["n"] == n else ""
        labels.append(
            f"      <div{active}><b>{lv['n']}</b>{zh_en(lv['zh'], lv['en'])}</div>"
        )

    # --- act chips ---
    chips = [
        f'        <span class="chip">{zh_en(z, e)}</span>'
        for z, e in zip(cur["chips_zh"], cur["chips_en"])
    ]

    # --- level cards ---
    cards = []
    for lv in levels:
        current = " current" if lv["n"] == n else ""
        dark = " d2" if lv["ink"] == "dark" else ""
        cards.append(
            f'      <div class="lv{current}">\n'
            f'        <div class="lv-top"><span class="lv-dot{dark}" '
            f'style="background:var({lv["color"]})">{lv["n"]}</span>'
            f"<div><h3>{zh_en(lv['zh'], lv['en'])}</h3>"
            f'<span class="lv-en">{zh_en(lv["sub"], lv["zh"])}</span></div></div>\n'
            f"        <p>{zh_en(lv['trigger_zh'], lv['trigger_en'])}</p>\n"
            f'        <p class="do"><b><span class="zh">行動：</span>'
            f'<span class="en">Do: </span></b>{zh_en(lv["do_zh"], lv["do_en"])}</p>\n'
            f"      </div>"
        )

    # --- indicator board ---
    board = []
    for cat in cats:
        rows = []
        for ind in (i for i in inds if i["category"] == cat["id"]):
            links = "".join(
                f' <a href="{safe_url(s["url"])}" target="_blank" rel="noopener">'
                f"[{esc(urlparse(s['url']).netloc.replace('www.', ''))}]</a>"
                for s in ind["sources"]
            )
            a = ind["analog"]
            if a.get("special"):
                tag = f"<b>{zh_en(a['label_zh'], a['label_en'])}</b>{zh_en(a['zh'], a['en'])}"
            else:
                tag = f"<b>{esc(a['label'])}</b>{zh_en(a['zh'], a['en'])}"
            rows.append(
                f'      <div class="ind"><span class="pip{PIP_CLASS[ind["status"]]}"></span>'
                f'<div><div class="ind-name">{zh_en(ind["name_zh"], ind["name_en"])}</div>'
                f'<div class="ind-note">{zh_en(ind["note_zh"], ind["note_en"])}{links}</div></div>'
                f'<div class="ustag">{tag}</div></div>'
            )
        board.append(
            f'    <div class="cat">\n'
            f'      <div class="cat-h"><h3>{zh_en(cat["zh"], cat["en"])}</h3>'
            f"<span>{esc(cat['tag'])}</span></div>\n" + "\n".join(rows) + "\n    </div>"
        )

    # --- timeline ---
    tl = []
    tags = data["timeline"]["tags"]
    for idx, ev in enumerate(data["timeline"]["events"]):
        war = ev["tag"] == "war"
        path = WAR_CIRCLE_PATH if war else CIRCLE_PATHS[idx % len(CIRCLE_PATHS)]
        dday = f"D−{ev['dday']}" if ev["dday"] else "D−0"
        tag_span = (
            ""
            if war
            else f'<span class="ev-tag">{zh_en(tags[ev["tag"]]["zh"], tags[ev["tag"]]["en"])}</span>'
        )
        tl.append(
            f'      <div class="ev{" war" if war else ""}">'
            f'<div class="ev-date">{circled(ev["date"], path)}'
            f'<span class="dday">{dday}</span></div>'
            f'<div class="ev-t">{zh_en(ev["zh"], ev["en"])}{tag_span}</div></div>'
        )

    demo = meta["demo"]
    demo_badge = (
        '<span class="demo-badge">'
        + zh_en("設計示意 · 非真實評估", "DESIGN MOCKUP · NOT A REAL ASSESSMENT")
        + "</span>"
        if demo
        else ""
    )
    foot_right = (
        zh_en(f"設計示意稿 · {date} · 資料皆為示意", f"Design mockup · {date} · all data illustrative")
        if demo
        else zh_en(f"最後審視 {date} · 非官方資訊站", f"Last reviewed {date} · unofficial")
    )
    title = (
        "台海燈號 Strait Signal — 設計示意 Demo"
        if demo
        else "台海燈號 Strait Signal — 戰爭從未突然爆發"
    )
    favicon = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='42' "
        f"fill='%23{LEVEL_HEX[n]}'/%3E%3C/svg%3E"
    )

    why_zh = (
        f"{c['total']} 項指標中：{c['signs']} 項出現跡象、"
        f"{c['triggered']} 項已觸發、{c['evac_triggered']} 項撤離級訊號。"
    )
    why_en = (
        f"Of {c['total']} indicators: {c['signs']} showing signs, "
        f"{c['triggered']} triggered, {c['evac_triggered']} evacuation-class signals."
    )

    out = (ROOT / "site" / "template.html").read_text()
    subs = {
        "{{TITLE}}": esc(title),
        "{{FAVICON}}": favicon,
        "{{BODY_STYLE}}": f"--cur:var({cur['color']});--curt:var({cur['track']})",
        "{{N}}": str(n),
        "{{LEVEL_ZH}}": esc(cur["zh"]),
        "{{LEVEL_EN}}": esc(cur["en"]),
        "{{LEVEL_SUB}}": esc(cur["sub"]),
        "{{BADGE_INK}}": f"ink-{cur['ink']}",
        "{{BADGE_ZH}}": esc(cur["badge_zh"]),
        "{{BADGE_EN}}": esc(cur["badge_en"]),
        "{{DESC_ZH}}": esc(cur["desc_zh"]),
        "{{DESC_EN}}": esc(cur["desc_en"]),
        "{{DATE}}": esc(date),
        "{{CADENCE_ZH}}": esc(meta["cadence_zh"]),
        "{{CADENCE_EN}}": esc(meta["cadence_en"]),
        "{{DEMO_BADGE}}": demo_badge,
        "{{METER_SEGS}}": "\n".join(segs),
        "{{METER_LABELS}}": "\n".join(labels),
        "{{WHY_ZH}}": esc(why_zh),
        "{{WHY_EN}}": esc(why_en),
        "{{ACT_CHIPS}}": "\n".join(chips),
        "{{LEVEL_CARDS}}": "\n".join(cards),
        "{{INDICATOR_BOARD}}": "\n".join(board),
        "{{RULE_ZH}}": esc(data["levels"]["rule_zh"]),
        "{{RULE_EN}}": esc(data["levels"]["rule_en"]),
        "{{TIMELINE}}": "\n".join(tl),
        "{{THREADS_URL}}": safe_url(meta["threads_url"]) if meta["threads_url"] != "#" else "#",
        "{{FOOT_RIGHT}}": foot_right,
    }
    for token, value in subs.items():
        assert token in out, f"template missing token {token}"
        out = out.replace(token, value)
    leftover = [t for t in ("{{",) if t in out]
    assert not leftover, "unreplaced tokens remain in output"

    dist = ROOT / "site" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / "index.html"
    target.write_text(out)
    return target


if __name__ == "__main__":
    path = build()
    print(f"built {path}")
