#!/usr/bin/env python3
"""Yeni marka kimliğine göre kapanış kartları (1080x1920) — YouTube (Abone Ol)
ve Instagram (Takip Et) için ayrı CTA."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import custom_visuals as cv

BG1, BG2, ACCENT, ACCENT2 = "#0b1220", "#14213d", "#ffb100", "#7fa3ff"


def _html(cta_icon, cta_text, cta_color, handle):
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ width:1080px;height:1920px;font-family:'DejaVu Sans',Arial,sans-serif;
  background:linear-gradient(160deg, {BG1} 0%, {BG2} 100%); position:relative; overflow:hidden; }}
.grid {{ position:absolute; inset:-60px; opacity:0.06;
  background-image:linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px);
  background-size:64px 64px; }}
.glow {{ position:absolute; top:480px; left:50%; margin-left:-450px; width:900px;height:900px;
  border-radius:50%; background:radial-gradient(circle, {ACCENT}35 0%, transparent 70%); }}
.wrap {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.logo {{ width:300px;height:300px;border-radius:50%;
  background: radial-gradient(circle at 50% 38%, {BG2} 0%, {BG1} 75%);
  border:5px solid {ACCENT}; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.mono {{ color:{ACCENT}; font-weight:900; font-size:96px; letter-spacing:-2px; line-height:1; }}
.sub {{ color:{ACCENT2}; font-weight:800; font-size:18px; letter-spacing:3px; margin-top:2px; }}
.title {{ color:#f2f5fb; font-weight:900; font-size:68px; margin-top:56px; text-align:center; letter-spacing:0.5px; }}
.tag {{ color:{ACCENT2}; font-weight:700; font-size:30px; margin-top:16px; text-align:center; }}
.cta {{ margin-top:90px; background:{cta_color}; color:#10131c; font-weight:900; font-size:52px;
  padding:26px 56px; border-radius:999px; letter-spacing:1px; }}
.handle {{ color:#5a6d94; font-weight:700; font-size:26px; margin-top:34px; letter-spacing:2px; }}
</style></head><body>
<div class="grid"></div><div class="glow"></div>
<div class="wrap">
  <div class="logo"><div class="mono">TBM</div><div class="sub">TÜRKİYE</div></div>
  <div class="title">TÜRKİYE BİLGİ MERKEZİ</div>
  <div class="tag">Bilmeniz gereken pratik bilgiler</div>
  <div class="cta">{cta_icon} {cta_text}</div>
  <div class="handle">{handle}</div>
</div>
</body></html>"""


def render(html, out_path):
    browser = cv._get_browser()
    page = browser.new_page(viewport={"width": 1080, "height": 1920})
    try:
        page.set_content(html, wait_until="load")
        page.screenshot(path=out_path)
    finally:
        page.close()


if __name__ == "__main__":
    render(_html("🔔", "ABONE OL", "#ffb100", "@turkiyebilgimerkezi · YouTube"), "out/endcard_youtube_new.png")
    render(_html("➡️", "TAKİP ET", "#ffb100", "@hakanerbasss · Instagram"), "out/endcard_tr_new.png")
    cv.close_browser()
    print("OK")
