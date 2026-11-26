#!/usr/bin/env python3
"""Short, filmed-looking loops of a plugin's panel for the website (H.264 MP4, no sound).

  make_video.py vst  PANEL.png           OUT.mp4   an establishing move, then close-ups of the busiest parts
  make_video.py pages PAGE1.png PAGE2... OUT.mp4   a tour through the MPC's pages, each with its name

Every film is different: the shots (push in, pull out, pan, tilt, diagonal glide, rack focus), their order,
lengths and the cuts between them (crossfade, dip to black, whip) are chosen from the file name as a seed,
so a plugin always gets the same film and no two plugins get the same one. The loop ends where it starts.
"""
import hashlib, random, subprocess, sys
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont

W, H, FPS = 1152, 648, 30


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def ease_io(t):
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * np.cos(np.pi * t)


def crop(src, cx, cy, zoom):
    sw, sh = src.size
    vw = sw / zoom
    vh = vw * H / W
    if vh > sh:
        vh = sh / max(zoom, 1.0)
        vw = vh * W / H
    x0 = min(max(cx * sw - vw / 2, 0), max(sw - vw, 0))
    y0 = min(max(cy * sh - vh / 2, 0), max(sh - vh, 0))
    return src.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + vw, y0 + vh))


_vign = None
_grid = None
def finish(fr, dof=0.0, focus=0.0, sweep=None, sweep_dir=1):
    """depth of field around the band at `focus` (-1 top .. 1 bottom), vignette, a light sweep"""
    global _vign, _grid
    if _grid is None:
        _grid = np.mgrid[0:H, 0:W]
    if dof > 0.01:
        blur = fr.filter(ImageFilter.GaussianBlur(2.0 + 4 * dof))
        y = np.linspace(-1, 1, H)[:, None]
        m = np.clip((np.abs(y - focus) - (0.40 - 0.12 * dof)) / 0.35, 0, 1) * dof
        mask = Image.fromarray((np.repeat(m, W, axis=1) * 255).astype(np.uint8))
        fr = Image.composite(blur, fr, mask)
    if _vign is None:
        yy, xx = np.mgrid[-1:1:H * 1j, -1:1:W * 1j]
        _vign = (1 - 0.36 * np.clip((xx ** 2 * 0.55 + yy ** 2) - 0.25, 0, 1))[..., None]
    a = np.asarray(fr).astype(np.float32) * _vign
    if sweep is not None:
        yy, xx = _grid
        xs = xx if sweep_dir > 0 else (W - xx)
        d = (xs + yy * 0.6) / (W + H * 0.6) - sweep
        a += (np.exp(-(d / 0.05) ** 2) * 34)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def hot_spots(src, zoom, n):
    g = src.convert("L").resize((320, int(320 * src.height / src.width)))
    e = np.asarray(g.filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    gh, gw = e.shape
    vw = gw / zoom
    vh = min(gh, vw * H / W)
    best = []
    for cy in np.linspace(vh / 2, gh - vh / 2, 9):
        for cx in np.linspace(vw / 2, gw - vw / 2, 13):
            x0, y0 = int(cx - vw / 2), int(cy - vh / 2)
            best.append((e[y0:int(y0 + vh), x0:int(x0 + vw)].mean(), cx / gw, cy / gh))
    best.sort(reverse=True)
    picked = []
    for s, cx, cy in best:
        if all(abs(cx - px) > 0.8 / zoom or abs(cy - py) > 0.45 for px, py in picked):
            picked.append((cx, cy))
        if len(picked) == n:
            break
    return picked or [(0.5, 0.5)]


def L(p, q, t):
    return p + (q - p) * ease_io(t)


# ---- close-up shots: each returns t (0..1) -> (cx, cy, zoom, dof, focus)
def shot(kind, c, z, rnd):
    cx, cy = c
    d = rnd.choice([-1, 1])
    e = rnd.choice([-1, 1])
    a = rnd.uniform(0.05, 0.09)
    if kind == "push":
        return lambda t: (cx, cy, L(z * 0.86, z * 1.08, t), 0.75, 0.0)
    if kind == "pull":
        return lambda t: (cx, cy, L(z * 1.12, z * 0.88, t), 0.75, 0.0)
    if kind == "pan":
        return lambda t: (L(cx - d * a, cx + d * a, t), cy, z, 0.8, 0.0)
    if kind == "tilt":
        return lambda t: (cx, L(cy - d * a, cy + d * a, t), z * 1.05, 0.8, 0.0)
    if kind == "diag":
        return lambda t: (L(cx - d * a, cx + d * a, t), L(cy - e * a * .7, cy + e * a * .7, t), L(z, z * 1.06, t), 0.8, 0.0)
    if kind == "rack":
        return lambda t: (L(cx - d * 0.02, cx + d * 0.02, t), cy, z, 1.0, L(-0.45 * d, 0.45 * d, t))
    raise ValueError(kind)


def wide(kind, rnd):
    d = rnd.choice([-1, 1])
    if kind == "push":
        return lambda t: (0.5, 0.5, L(1.0, 1.14, t), 0.0, 0.0)
    if kind == "pull":
        return lambda t: (0.5, 0.5, L(1.18, 1.0, t), 0.0, 0.0)
    return lambda t: (L(0.5 - d * 0.04, 0.5 + d * 0.04, t), 0.5, 1.12, 0.0, 0.0)


def writer(out):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                             "-tune", "film", "-crf", "26", "-g", str(FPS * 2), "-pix_fmt", "yuv420p",
                             "-movflags", "+faststart", "-an", out], stdin=subprocess.PIPE)


def render(out, pieces, rnd, labels=None):
    """pieces: (seconds, source image, fn, cut into the next one)"""
    p = writer(out)
    font = None
    if labels:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 24)
        except OSError:
            pass
    seq, starts = [], []
    for i, (dur, src, fn, cut) in enumerate(pieces):
        starts.append(len(seq))
        n = int(dur * FPS)
        for k in range(n):
            seq.append((i, k / max(1, n - 1)))
    total = len(seq)

    def view(idx):
        i, t = seq[idx % total]
        dur, src, fn, cut = pieces[i]
        cx, cy, z, dof, foc = fn(t)
        return crop(src, cx, cy, z), dof, foc, i

    sweeps = sorted(rnd.sample(range(total), k=min(2, max(1, total // (FPS * 6)))))
    sdir = rnd.choice([-1, 1])
    for idx in range(total):
        im, dof, foc, i = view(idx)
        cut = pieces[i][3]
        nf = {"fade": int(0.6 * FPS), "dip": int(0.7 * FPS), "whip": int(0.35 * FPS)}[cut]
        nxt = starts[i + 1] if i + 1 < len(pieces) else 0
        end = starts[i + 1] if i + 1 < len(pieces) else total
        left = end - idx
        lab_i = i
        if left <= nf:
            im2, dof2, foc2, j = view(nxt + (nf - left))
            a = ease(1 - left / nf)
            if cut == "fade":
                im = Image.blend(im, im2, a)
            elif cut == "dip":
                black = Image.new("RGB", (W, H))
                im = Image.blend(im, black, min(1.0, a * 2)) if a < 0.5 else Image.blend(black, im2, (a - 0.5) * 2)
            else:
                off = int(a * W)
                strip = Image.new("RGB", (W * 2, H))
                strip.paste(im, (0, 0)); strip.paste(im2, (W, 0))
                im = strip.crop((off, 0, off + W, H))
                r = int(18 * np.sin(np.pi * a))
                if r > 0:
                    im = im.filter(ImageFilter.BoxBlur(r))
            dof += (dof2 - dof) * a
            foc += (foc2 - foc) * a
            if a > 0.5:
                lab_i = j
        sw = None
        for s0 in sweeps:
            s = (idx - s0) / (1.4 * FPS)
            if -0.2 < s < 1.2:
                sw = s
        fr = finish(im, dof, foc, sw, sdir)
        if labels and font:
            d = ImageDraw.Draw(fr)
            lab = labels[lab_i]
            tw = d.textlength(lab, font=font)
            d.rectangle((28, H - 68, 28 + tw + 26, H - 28), fill=(0, 0, 0), outline=(0, 246, 255), width=2)
            d.text((41, H - 64), lab, font=font, fill=(0, 246, 255))
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()


def seed_of(name):
    return int(hashlib.sha1(name.encode()).hexdigest()[:8], 16)


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[-1]
    rnd = random.Random(seed_of(out.rsplit("/", 1)[-1]))
    cuts = ["fade", "fade", "dip", "whip"]
    if mode == "vst":
        src = Image.open(sys.argv[2]).convert("RGB")
        n = rnd.choice([2, 3, 3, 4])
        spots = hot_spots(src, 2.4, n)
        rnd.shuffle(spots)
        kinds = rnd.sample(["push", "pull", "pan", "tilt", "diag", "rack"], k=len(spots))
        pieces = [(rnd.uniform(2.6, 3.6), src, wide(rnd.choice(["push", "pull", "drift"]), rnd), rnd.choice(cuts))]
        for s, k in zip(spots, kinds):
            pieces.append((rnd.uniform(2.8, 4.0), src, shot(k, s, rnd.uniform(2.0, 2.8), rnd), rnd.choice(cuts)))
        if rnd.random() < 0.5:
            pieces.insert(rnd.randint(2, len(pieces)), (2.4, src, wide("drift", rnd), "fade"))
        pieces[-1] = pieces[-1][:3] + ("fade",)
        render(out, pieces, rnd)
    elif mode == "pages":
        files = sys.argv[2:-1]
        pieces, labels = [], []
        for f in files:
            im = Image.open(f).convert("RGB")
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
            labels.append(f.rsplit("/", 1)[-1].rsplit(".", 1)[0].split("_", 1)[-1].replace("-", " "))
            kind = rnd.choice(["push", "pull", "panl", "panr", "drift"])
            fn = {
                "push": lambda t: (0.5, 0.5, L(1.0, 1.08, t), 0.0, 0.0),
                "pull": lambda t: (0.5, 0.5, L(1.09, 1.0, t), 0.0, 0.0),
                "panl": lambda t: (L(0.56, 0.44, t), 0.5, 1.02, 0.0, 0.0),
                "panr": lambda t: (L(0.44, 0.56, t), 0.5, 1.02, 0.0, 0.0),
                "drift": lambda t: (L(0.47, 0.53, t), L(0.48, 0.52, t), 1.05, 0.0, 0.0),
            }[kind]
            pieces.append((rnd.uniform(2.2, 3.1), im, fn, rnd.choice(cuts)))
        pieces[-1] = pieces[-1][:3] + ("fade",)
        render(out, pieces, rnd, labels=labels)
    print("wrote", out)
