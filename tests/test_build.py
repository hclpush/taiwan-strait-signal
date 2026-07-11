import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "pipeline"))

import json  # noqa: E402

from build import build, esc, safe_url  # noqa: E402
from levels import compute_level  # noqa: E402


def test_esc_blocks_html_injection():
    assert esc('<script>alert("x")</script>') == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    )


def test_safe_url_rejects_non_http():
    assert safe_url("javascript:alert(1)") == "#"
    assert safe_url("https://reuters.com/a") == "https://reuters.com/a"


def test_build_output_is_complete():
    target = build()
    html = target.read_text()
    inds = json.loads((ROOT / "data" / "indicators.json").read_text())["indicators"]
    n = compute_level(inds)
    assert "{{" not in html, "unreplaced template tokens"
    assert f"目前第 {n} 級" in html
    assert html.count('class="ind"') == len(inds) == 14
    events = html.count('<div class="ev">') + html.count('<div class="ev war">')
    assert events == 13  # timeline events
    assert "戰爭從未突然爆發" in html
    # every status pip rendered matches data
    signs = sum(1 for i in inds if i["status"] == 1)
    assert html.count('class="pip half"') == signs + 1  # +1 legend key
