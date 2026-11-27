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
        for art in re.finditer(r'<article class="card" data-repo="([^"]+)"([^>]*)>(.*?)</article>', body, re.S):
            repo, attrs, a = art.group(1), art.group(2), art.group(3)
            c = out.setdefault(repo, {"areas": []})
            m = re.search(r'data-was="([^"]+)"', attrs)   # a renamed repo: its old name, so it is not announced as new
            if m:
                c["was"] = m.group(1)
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

def intro(what):
    """one short sentence for new readers: what the instrument is"""
    m = re.match(r"(.+?[.!?:])(\s|$)", what)
    one = (m.group(1) if m else what).rstrip(":")
    return one if len(one) <= 160 else one[:157].rsplit(" ", 1)[0] + "…"

def clean(notes):
    notes = re.sub(r"🤖 Generated with.*", "", notes or "", flags=re.S)
    notes = re.sub(r"https://claude\.ai/\S+", "", notes)
    notes = re.sub(r"^(Co-Authored-By|Claude-Session):.*$", "", notes, flags=re.M | re.I)
    notes = re.sub(r"^#{1,6}\s*(.+?)\s*$", r"**\1**", notes, flags=re.M)   # Markdown headings: Discord shows them huge
    return re.sub(r"\n{3,}", "\n\n", notes).strip()

def changes(repo, was, tag):
    """no release notes written: the commit titles between the two releases"""
    if not was:
        return ""
    req = urllib.request.Request(f"https://api.github.com/repos/{OWNER}/{repo}/compare/{was}...{tag}",
                                 headers={"User-Agent": "swtdr34mz-site", "Accept": "application/vnd.github+json"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        print(f"  {repo}: no commit list ({e})")
        return ""
    out = []
    for c in data.get("commits", []):
        msg = c["commit"]["message"].strip().split("\n")
        if msg[0].startswith("Merge pull request"):
            title = next((l.strip() for l in msg[1:] if l.strip()), "")
        elif msg[0].startswith("Merge "):
            continue
        else:
            title = msg[0].strip()
        if title and title not in out and not re.match(r"(?i)(bump|release|version)\b.*\d", title):
            out.append(title)
    return "\n".join(f"• {t}" for t in out[-12:])

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
    for repo, c0 in info.items():           # a renamed repo: what the page showed under its old name
        if repo not in old and c0.get("was") in old:
            old[repo] = old[c0["was"]]
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
            if first:
                lines.append(c["what"])            # a new instrument: the whole description
                notes = clean(rel.get("notes"))
                if notes:
                    lines.append("")
                    lines.append(notes[:1500])
            else:
                lines.insert(0, f"*{intro(c['what'])}*")   # one line for new readers, then what changed
                notes = clean(rel.get("notes")) or changes(repo, was, rel["tag"])
                lines.append("")
                if notes:
                    if not notes.startswith("**"):        # the notes bring no heading of their own
                        lines.append(f"**What's new in {rel['tag']}**")
                    lines.append(notes[:2500])
                else:
                    lines.append(f"Details on the [release page]({rel['url']}).")
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
