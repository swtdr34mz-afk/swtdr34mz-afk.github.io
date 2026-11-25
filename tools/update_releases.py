#!/usr/bin/env python3
"""Writes releases.json: the newest release of every project on the page.

The projects are the data-repo="..." cards in index.html, so a new card is
picked up automatically. Runs in the GitHub Action (see .github/workflows).
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

OWNER = os.environ.get("OWNER", "swtdr34mz-afk")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = sys.argv[1] if len(sys.argv) > 1 else "releases.json"

html = open("index.html", encoding="utf-8").read()
repos = sorted(set(re.findall(r'data-repo="([^"]+)"', html)))

def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print(f"  {url}: {e}")
        return None

data = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "repos": {}}
for repo in repos:
    rel = get(f"https://api.github.com/repos/{OWNER}/{repo}/releases/latest")
    if not rel or "tag_name" not in rel:
        print(f"{repo}: no release")
        continue
    data["repos"][repo] = {
        "tag": rel["tag_name"],
        "date": rel.get("published_at"),
        "url": rel.get("html_url"),
        "assets": {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])},
        "notes": (rel.get("body") or "")[:900],
    }
    print(f"{repo}: {rel['tag_name']}")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=1)
