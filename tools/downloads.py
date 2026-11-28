#!/usr/bin/env python3
"""Writes downloads.json: how often every project on the page was downloaded,
counted the same way as in update_releases.py (all releases, MPC files apart,
data files not counted). Runs every 10 minutes (.github/workflows/downloads.yml);
the page reads it directly, so the counter moves without rebuilding the site."""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

OWNER = os.environ.get("OWNER", "swtdr34mz-afk")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = sys.argv[1] if len(sys.argv) > 1 else "downloads.json"
repos = sorted(set(re.findall(r'data-repo="([^"]+)"', open("index.html", encoding="utf-8").read())))

def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "repos": {}}
for repo in repos:
    dl, page = {"mpc": 0, "main": 0}, 1
    try:
        while True:
            rels = get(f"https://api.github.com/repos/{OWNER}/{repo}/releases?per_page=100&page={page}") or []
            for r in rels:
                for a in r.get("assets", []):
                    name = a["name"].lower()
                    if not name.endswith(".json"):
                        dl["mpc" if "mpc" in name else "main"] += a.get("download_count", 0)
            if len(rels) < 100:
                break
            page += 1
    except Exception as e:                # one project not reachable: left out (the page keeps its last number)
        print(f"{repo}: {e}")
        continue
    try:                                  # the newest release's Linux file, so the page can show its button early
        rel = get(f"https://api.github.com/repos/{OWNER}/{repo}/releases/latest")
        lin = [a["browser_download_url"] for a in rel.get("assets", []) if "linux" in a["name"].lower()]
        if lin:
            dl["linux"] = lin[0]
    except Exception:
        pass
    if dl["mpc"] or dl["main"] or "linux" in dl:
        out["repos"][repo] = dl
# the history for the live displays (feed, "+N today", HOT, the 24-hour curve): a snapshot of every
# project's count whenever the total changed, kept for 26 hours. PREV is the last downloads.json.
now = int(datetime.now(timezone.utc).timestamp())
try:
    hist = json.load(open(os.environ.get("PREV", ""), encoding="utf-8")).get("hist", [])
except Exception:
    hist = []
hist = [h for h in hist if now - h["t"] < 26 * 3600]
snap = {r: [d["main"], d["mpc"]] for r, d in out["repos"].items() if d["main"] or d["mpc"]}
if hist:                                  # a project that could not be read this time keeps its last count
    for r, v in hist[-1]["r"].items():
        snap.setdefault(r, v)
if not hist or snap != hist[-1]["r"]:
    hist.append({"t": now, "r": snap})
out["hist"] = hist
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(",", ":"))
print(sum(d["mpc"] + d["main"] for d in out["repos"].values()), "downloads")
