#!/usr/bin/env python3
"""Kanal logosu (800x800) ve banner'ı (2560x1440) üretir — video kartlarıyla
aynı marka dilinde (koyu lacivert + altın gradyan)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import custom_visuals as cv

BG1, BG2, ACCENT, ACCENT2 = "#0b1220", "#14213d", "#ffb100", "#7fa3ff"

LOGO_HTML = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ width:800px;height:800px;font-family:'DejaVu Sans',Arial,sans-serif; }}
.logo {{
  width:800px;height:800px;border-radius:50%;
  background: radial-gradient(circle at 50% 38%, {BG2} 0%, {BG1} 75%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  position:relative; overflow:hidden;
}}
.ring {{ position:absolute; inset:26px; border-radius:50%; border:6px solid {ACCENT}; opacity:0.9; }}
.mono {{ color:{ACCENT}; font-weight:900; font-size:260px; letter-spacing:-6px; line-height:1; margin-top:-10px; }}
.sub {{ color:{ACCENT2}; font-weight:800; font-size:44px; letter-spacing:6px; margin-top:6px; }}
</style></head><body>
<div class="logo"><div class="ring"></div><div class="mono">TBM</div><div class="sub">TÜRKİYE</div></div>
</body></html>"""

BANNER_HTML = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ width:2560px;height:1440px;font-family:'DejaVu Sans',Arial,sans-serif;
  background:linear-gradient(160deg, {BG1} 0%, {BG2} 100%); position:relative; overflow:hidden; }}
.grid {{ position:absolute; inset:-100px; opacity:0.06;
  background-image:linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px);
  background-size:80px 80px; }}
.glow {{ position:absolute; top:-300px; left:50%; margin-left:-700px; width:1400px;height:1400px;
  border-radius:50%; background:radial-gradient(circle, {ACCENT}30 0%, transparent 70%); }}
.safe {{ position:absolute; left:507px; top:508px; width:1546px; height:423px;
  display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }}
.badge {{ background:{ACCENT}; color:#10131c; font-weight:900; font-size:32px; padding:10px 30px;
  border-radius:999px; letter-spacing:2px; margin-bottom:22px; }}
.title {{ color:#f2f5fb; font-weight:900; font-size:96px; letter-spacing:1px; }}
.tag {{ color:{ACCENT2}; font-weight:700; font-size:38px; margin-top:18px; letter-spacing:1px; }}
.handle {{ color:#5a6d94; font-weight:700; font-size:30px; margin-top:14px; letter-spacing:3px; }}
</style></head><body>
<div class="grid"></div><div class="glow"></div>
<div class="safe">
  <div class="badge">BİLİYOR MUYDUNUZ?</div>
  <div class="title">TÜRKİYE BİLGİ MERKEZİ</div>
  <div class="tag">Bilmeniz gereken pratik bilgiler</div>
  <div class="handle">@turkiyebilgimerkezi</div>
</div>
</body></html>"""


def render(html, w, h, out_path):
    browser = cv._get_browser()
    page = browser.new_page(viewport={"width": w, "height": h})
    try:
        page.set_content(html, wait_until="load")
        page.screenshot(path=out_path)
    finally:
        page.close()


if __name__ == "__main__":
    render(LOGO_HTML, 800, 800, "out/logo.png")
    render(BANNER_HTML, 2560, 1440, "out/banner.png")
    cv.close_browser()
    print("OK")
