#!/usr/bin/env python3
"""Lists the plugins on the page for the video workflow: the repos of the VST and the MPC cards, and each card's
picture (the fallback when a repo cannot draw its own panel).  video_plan.py vst|mpc|all  ->  JSON"""
import json, re, sys
from pathlib import Path
html = (Path(__file__).resolve().parent.parent / "index.html").read_text(encoding="utf-8")
def cards(sec):
    a = html.index(f'<section id="{sec}"'); b = html.index("</section>", a)
    return [{"repo": r, "img": i} for r, i in
            re.findall(r'data-repo="([^"]+)"[^>]*>\s*<div class="shot"><img src="([^"]+)"', html[a:b])]
what = sys.argv[1] if len(sys.argv) > 1 else "all"
out = {"vst": cards("vst"), "mpc": cards("mpc")}
print(json.dumps(out[what] if what in out else out))
