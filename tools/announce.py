#!/usr/bin/env python3
"""Posts new releases to the Discord server's #announcements channels.

Compares the releases.json that is live on the site (what visitors saw until
now) with the one just built. Every project with a new tag gets a post in the
announcements channel of its area: the card's section on the page decides
(vst, mpc, fm1; a project in two sections is posted in both). A project that
was not on the page before is announced as a new instrument.

The channels are Discord webhooks, kept as repository secrets:
  DISCORD_WEBHOOK_VST, DISCORD_WEBHOOK_MPC, DISCORD_WEBHOOK_FM1
A missing secret: that area is skipped. Without the old file (first run, or
the site unreachable) nothing is posted, so nothing is announced twice.

  python3 tools/announce.py OLD.json NEW.json [--force REPO,REPO] [--only vst,mpc,fm1] [--dry]
"""
import html as htmlmod, json, os, re, sys, urllib.request

SITE = "https://swtdr34mz-afk.github.io/"
OWNER = "swtdr34mz-afk"
AREA = {"vst": "VST plugin", "mpc": "MPC plugin", "fm1": "FM-1 mod"}
COLOR = 0x22E5FF                        # the cyan of the site

def text(s):
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", s)).strip()

def cards():
    """repo -> {name, what, img, play, areas}, from index.html"""
    page = open("index.html", encoding="utf-8").read()
    out = {}
    for sec in re.finditer(r'<section id="(\w+)">(.*?)</section>', page, re.S):
        area, body = sec.group(1), sec.group(2)
        if area not in AREA:
            continue
        for art in re.finditer(r'<article class="card" data-repo="([^"]+)"[^>]*>(.*?)</article>', body, re.S):
            repo, a = art.group(1), art.group(2)
            c = out.setdefault(repo, {"areas": []})
            c["areas"].append(area)
            m = re.search(r"<h3>(.*?)<span", a, re.S)
            c["name"] = text(m.group(1)) if m else repo
            m = re.search(r"<p>(.*?)</p>", a, re.S)
            c["what"] = text(m.group(1)) if m else ""
            m = re.search(r'<img src="([^"]+)"', a)
            c["img"] = SITE + m.group(1) if m else None
            m = re.search(r'href="([^"]+/emu/)"', a)
            c["play"] = m.group(1) if m else None
            c.setdefault("by", {})[area] = {"what": c["what"], "img": c["img"]}   # each section's own text and picture
    return out

def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("repos", {})
    except Exception:
        return None

def post(hook, payload, dry):
    if dry:
        print(json.dumps(payload, indent=1, ensure_ascii=False))
        return
    req = urllib.request.Request(hook, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "swtdr34mz-site"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("  posted", r.status)

def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    force = []
    if "--force" in args:
        force = [x.strip() for x in args[args.index("--force") + 1].split(",") if x.strip()]
    only = []                           # (by hand: post only in these areas' channels)
    if "--only" in args:
        only = [x.strip().lower() for x in args[args.index("--only") + 1].split(",") if x.strip()]
    old, new = load(args[0]), load(args[1])
    if new is None:
        print("no new releases.json")
        return
    if old is None and not force:
        print("no old releases.json: nothing announced (so nothing twice)")
        return
    old = old or {}
    info = cards()
    for repo, rel in sorted(new.items()):
        was = old.get(repo, {}).get("tag")
        if rel["tag"] == was and repo not in force:
            continue
        c = info.get(repo)
        if not c:
            continue
        first = repo not in old
        title = f"{c['name']} {rel['tag']}"
        lines = []
        again = not first and was == rel["tag"]   # by hand (--force): the same release once more
        if first:
            lines.append(f"**New {', '.join(AREA[a] for a in c['areas'])}!**")
        elif again:
            lines.append(f"**Out now** ({', '.join(AREA[a] for a in c['areas'])})")
        elif was:
            lines.append(f"**Update:** {was} → {rel['tag']}")
        print(f"{title}: {'new' if first else 'update'} -> {', '.join(c['areas'])}")
        head = lines
        for area in c["areas"]:
            if only and area not in only:
                continue
            c["what"], c["img"] = c["by"][area]["what"], c["by"][area]["img"]
            lines = list(head)
            lines.append(c["what"])
            notes = re.sub(r"🤖 Generated with.*", "", rel.get("notes") or "", flags=re.S).strip()
            notes = re.sub(r"https://claude\.ai/\S+", "", notes).strip()
            if notes:
                lines.append("")
                lines.append(notes[:700])
            links = [f"[Download]({rel['url']})"]
            if c.get("play"):
                links.append(f"[▶ Play in your browser]({c['play']})")
            links.append(f"[Source](https://github.com/{OWNER}/{repo})")
            links.append(f"[All instruments]({SITE})")
            lines.append("")
            lines.append(" · ".join(links))
            embed = {"title": title, "url": rel["url"], "description": "\n".join(lines)[:4000], "color": COLOR}
            if c.get("img"):
                embed["image"] = {"url": c["img"]}
            payload = {"username": "swtdr34mz releases", "embeds": [embed],
                       "content": "🎉 New instrument out now!" if first else "🎉 Out now!" if again else "🔧 New update out now!"}
            hook = os.environ.get(f"DISCORD_WEBHOOK_{area.upper()}", "")
            if not hook and not dry:
                print(f"  no webhook for {area}: skipped")
                continue
            try:
                post(hook, payload, dry)
            except Exception as e:
                print(f"  {area}: {e}")

main()
