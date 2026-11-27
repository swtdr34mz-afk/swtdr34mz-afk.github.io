#!/usr/bin/env python3
"""Records a short moving loop of every FM-1 mod's screen from its browser emulator.

For each FM-1 card on the page that has a ▶ Play link (github.io/REPO/emu/), this opens the emulator in a
headless Chrome, switches it on, plays a few keys and grabs the 240 x 240 screen as frames. The frames become
img/anim/REPO.webp (an animated WebP that loops); img/anim/list.json names the ones that worked. The page swaps
the still screenshot for the loop when it finds it in that list.
"""
import base64, hashlib, io, json, re, sys, urllib.request
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "img" / "anim"
OUT.mkdir(parents=True, exist_ok=True)

html = (ROOT / "index.html").read_text(encoding="utf-8")
fm1 = html[html.index('<section id="fm1"'):]
fm1 = fm1[:fm1.index("</section>")]
emus = sorted(set(re.findall(r'https://swtdr34mz-afk\.github\.io/([A-Za-z0-9_.-]+)/emu/', fm1)))
# which emulators changed since their last recording: the newest commit of the mod's repo (every push rebuilds
# its browser emulator), so any change to the graphics or the code is noticed
import os
def fingerprint(repo):
    req = urllib.request.Request(f"https://api.github.com/repos/swtdr34mz-afk/{repo}/commits/HEAD",
                                 headers={"Accept": "application/vnd.github.sha"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        return urllib.request.urlopen(req, timeout=30).read().decode().strip()
    except Exception as e:
        print(repo, "fingerprint failed:", e)
        return None

FP = OUT / "fingerprints.json"
old_fp = json.loads(FP.read_text()) if FP.exists() else {}
new_fp = {r: fingerprint(r) for r in emus}
force = set(a for a in sys.argv[1:] if a != "--changed")
if "--changed" in sys.argv:
    emus = [e for e in emus if e in force or not (OUT / f"{e}.webp").exists()
            or (new_fp.get(e) and new_fp[e] != old_fp.get(e))]
elif force:
    emus = [e for e in emus if e in force]
print("recording:", emus)

# the screen as the page draws it, at up to 480 x 480 (high-resolution graphics stay sharp)
GRAB = """() => {
  const s = document.getElementById('screen') || document.querySelector('canvas');
  const n = Math.max(240, Math.min(480, s.width, s.height));
  const c = document.createElement('canvas'); c.width = c.height = n;
  const g = c.getContext('2d'); g.imageSmoothingEnabled = n > 240;
  g.imageSmoothingQuality = 'high';
  g.drawImage(s, 0, 0, n, n);
  return c.toDataURL('image/png');
}"""
KEY = """([code, down]) => {
  const t = document.getElementById('controls') || document.body;
  const ev = new KeyboardEvent(down ? 'keydown' : 'keyup', {code: code, key: code, bubbles: true});
  (down ? t : window).dispatchEvent(ev);
}"""

# what gets played while recording: frame number -> (key, down)
SCRIPT = {4: ("KeyP", True), 5: ("KeyP", False)}
notes = ["Digit1", "KeyQ", "KeyE", "Digit3", "KeyT", "Digit5", "KeyW", "KeyR"]
for i, code in enumerate(notes):
    SCRIPT[8 + i * 5] = (code, True)
    SCRIPT[11 + i * 5] = (code, False)

FRAMES, STEP_MS = 54, 110
done = {}
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    for repo in emus:
        url = f"https://swtdr34mz-afk.github.io/{repo}/emu/"
        print(repo, url, flush=True)
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        try:
            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_selector("#go:not([disabled])", timeout=60000)
            page.click("#go")
            page.wait_for_timeout(3500)            # boot and splash
            frames = []
            for f in range(FRAMES):
                if f in SCRIPT:
                    page.evaluate(KEY, list(SCRIPT[f]))
                data = page.evaluate(GRAB)
                frames.append(Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB"))
                page.wait_for_timeout(STEP_MS)
            # drop a fully black recording (the emulator did not start)
            if all(fr.getbbox() is None for fr in frames):
                print("  black, skipped")
                continue
            path = OUT / f"{repo}.webp"
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=STEP_MS, loop=0,
                           quality=72, method=6)
            # a still from the loop for the card's picture (and the strip of newest releases), so the page
            # never shows an old screenshot before the loop starts
            still = OUT / f"{repo}.png"
            frames[min(len(frames) - 1, 24)].save(still, optimize=True)
            # a version in the address, so browsers fetch the new loop instead of an old copy they kept
            ver = (new_fp.get(repo) or "")[:7] or str(int(path.stat().st_mtime))
            done[repo] = f"img/anim/{repo}.webp?v={ver}"
            print("  ok", path.stat().st_size // 1024, "KB")
        except Exception as e:
            print("  failed:", e)
        finally:
            page.close()
    browser.close()

# keep loops recorded earlier for mods that failed this time
old = {}
lst = OUT / "list.json"
if lst.exists():
    try:
        old = json.loads(lst.read_text())
    except Exception:
        pass
old.update(done)
old = {k: v for k, v in old.items() if (ROOT / v.split("?")[0]).exists()}
lst.write_text(json.dumps(old, indent=1, sort_keys=True) + "\n")
# the FM-1 cards' pictures: the newest still, with its version, written into index.html
page = (ROOT / "index.html").read_text(encoding="utf-8")
for r, v in old.items():
    ver = v.split("?v=")[-1] if "?v=" in v else ""
    if not (OUT / f"{r}.png").exists():
        continue
    page = re.sub(r'(data-repo="%s" data-asset="\.fwsc">\s*<div class="shot"><img src=")[^"]+(")' % re.escape(r),
                  lambda m: m.group(1) + f"img/anim/{r}.png?v={ver}" + m.group(2), page)
(ROOT / "index.html").write_text(page, encoding="utf-8")
for r in done:
    if new_fp.get(r):
        old_fp[r] = new_fp[r]
FP.write_text(json.dumps(old_fp, indent=1, sort_keys=True) + "\n")
print("list:", sorted(old))
