#!/usr/bin/env python3
"""Draws every page (tab) of an MPC plugin from its skin: mpc/plugin/skins/TUI.json and the PNGs next to it.

  mpc_pages.py SKINS_DIR OUT_DIR   ->  OUT_DIR/00_HOME.png, 01_OSC.png, ...  (1280 x 628, the MPC's plugin area)

Knobs are film strips (a frame is picked so they sit at lively, different positions); buttons that share a
parameter and a place show one of their states; images are drawn as they are.
"""
import json, re, sys, random
from pathlib import Path
from PIL import Image

skins, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
pd = json.loads((skins / "TUI.json").read_text(encoding="utf-8"))["pageData"]
local = {e["key"]: e["value"] for e in pd["componentDefinitions"]["localComponentDefinitions"]}
rnd = random.Random(7)
cache = {}

def img(name):
    if name not in cache:
        p = skins / name
        cache[name] = Image.open(p).convert("RGBA") if name and p.exists() else None
    return cache[name]

def bounds(c):
    x, y, w, h = (int(float(v)) for v in c["bounds"]["bounds"].split())
    return x, y, w, h

def draw_knob(canvas, data, x, y, w, h):
    strip = img(data.get("filmStrip", ""))
    if strip is None:
        return
    n = max(1, int(data.get("numFrames", 1)))
    fh = strip.height // n
    f = int(n * rnd.uniform(0.25, 0.8))
    frame = strip.crop((0, f * fh, strip.width, (f + 1) * fh))
    canvas.alpha_composite(frame, (x, y))

for ti, tab in enumerate(pd["tabs"]):
    name = tab["tabName"]
    W, H = 1280, 628
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    placed_buttons = set()
    placed_images = set()
    for c in tab["componentDefinition"]["componentsData"]:
        cd = c["componentData"]
        ty, data = cd["type"], cd.get("data", {})
        x, y, w, h = bounds(c)
        if ty == "Image":
            # several pictures in one place are the states of one display: draw only the first
            if (x, y, w, h) in placed_images and (w, h) != (1280, 628):
                continue
            placed_images.add((x, y, w, h))
            im = img(data.get("image", ""))
            if im is not None:
                if im.size != (w, h) and w > 0 and h > 0:
                    im = im.resize((w, h))
                canvas.alpha_composite(im, (x, y))
        elif ty == "Button":
            key = (data.get("handleName"), x, y)
            if key in placed_buttons:
                continue
            group = [cc for cc in tab["componentDefinition"]["componentsData"]
                     if cc["componentData"]["type"] == "Button"
                     and cc["componentData"]["data"].get("handleName") == data.get("handleName")
                     and bounds(cc)[:2] == (x, y)]
            pick = rnd.choice(group)["componentData"]["data"]
            im = img(pick.get("offImage") or pick.get("onImage") or "")
            if im is not None:
                canvas.alpha_composite(im if im.size == (w, h) else im.resize((w, h)), (x, y))
            placed_buttons.add(key)
        elif ty in local:
            for sub in local[ty]["componentsData"]:
                scd = sub["componentData"]
                sx, sy, sw, sh = bounds(sub)
                if scd["type"] == "Knob":
                    draw_knob(canvas, scd.get("data", {}), x + sx, y + sy, sw, sh)
                elif scd["type"] == "Image":
                    im = img(scd.get("data", {}).get("image", ""))
                    if im is not None:
                        canvas.alpha_composite(im, (x + sx, y + sy))
    safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
    canvas.convert("RGB").save(out / f"{ti:02d}_{safe}.png")
    print(out / f"{ti:02d}_{safe}.png")
