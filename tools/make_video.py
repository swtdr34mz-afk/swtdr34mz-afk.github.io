#!/usr/bin/env python3
"""Short, filmed-looking loops of a plugin's panel for the website (H.264 MP4, 1280 x 720, no sound).

  make_video.py vst  PANEL.png           OUT.mp4   a slow establishing move, then close-ups of the busiest parts
  make_video.py pages PAGE1.png PAGE2... OUT.mp4   a tour through the MPC's pages, each with its name

The look: soft camera moves with easing, a shallow depth of field (top and bottom gently out of focus in the
close-ups), a vignette and a light that sweeps across now and then. The loop ends where it starts.
"""
import subprocess, sys
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageChops

W, H, FPS = 1280, 720, 25


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def crop(src, cx, cy, zoom):
    """the view of src centred on (cx, cy) in 0..1, zoom 1 = the whole width fits"""
    sw, sh = src.size
    vw = sw / zoom
    vh = vw * H / W
    if vh > sh:                      # a wide panel: fit the height instead
        vh = sh / max(zoom, 1.0)
        vw = vh * W / H
    x0 = min(max(cx * sw - vw / 2, 0), max(sw - vw, 0))
    y0 = min(max(cy * sh - vh / 2, 0), max(sh - vh, 0))
    box = (x0, y0, x0 + vw, y0 + vh)
    return src.resize((W, H), Image.LANCZOS, box=box)


_vign = None
def finish(fr, dof=0.0, sweep=None):
    """depth of field, vignette, a light sweep (sweep = 0..1 position or None)"""
    global _vign
    if dof > 0.01:
        blur = fr.filter(ImageFilter.GaussianBlur(2.2 + 4 * dof))
        y = np.linspace(-1, 1, H)[:, None]
        m = np.clip((np.abs(y) - (0.42 - 0.12 * dof)) / 0.35, 0, 1) * dof
        mask = Image.fromarray((np.repeat(m, W, axis=1) * 255).astype(np.uint8))
        fr = Image.composite(blur, fr, mask)
    if _vign is None:
        yy, xx = np.mgrid[-1:1:H * 1j, -1:1:W * 1j]
        v = 1 - 0.38 * np.clip((xx ** 2 * 0.55 + yy ** 2) - 0.25, 0, 1)
        _vign = v[..., None]
    a = np.asarray(fr).astype(np.float32) * _vign
    if sweep is not None:
        yy, xx = np.mgrid[0:H, 0:W]
        d = (xx + yy * 0.6) / (W + H * 0.6) - sweep
        a += (np.exp(-(d / 0.05) ** 2) * 38)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def hot_spots(src, zoom, n=2):
    """the busiest parts of the panel (most edges) for close-ups, as centres in 0..1"""
    g = src.convert("L").resize((320, int(320 * src.height / src.width)))
    e = np.asarray(g.filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    gh, gw = e.shape
    vw = gw / zoom
    vh = min(gh, vw * H / W)
    best = []
    for cy in np.linspace(vh / 2, gh - vh / 2, 9):
        for cx in np.linspace(vw / 2, gw - vw / 2, 13):
            x0, y0 = int(cx - vw / 2), int(cy - vh / 2)
            s = e[y0:int(y0 + vh), x0:int(x0 + vw)].mean()
            best.append((s, cx / gw, cy / gh))
    best.sort(reverse=True)
    picked = []
    for s, cx, cy in best:
        if all(abs(cx - px) > 0.9 / zoom or abs(cy - py) > 0.5 for px, py in picked):
            picked.append((cx, cy))
        if len(picked) == n:
            break
    return picked or [(0.5, 0.5)]


def writer(out):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                             "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", out],
                            stdin=subprocess.PIPE)


def shots_vst(src):
    """(seconds, function t -> (cx, cy, zoom, dof)) pieces; crossfades in between"""
    a, b = hot_spots(src, 2.4)[:2] if len(hot_spots(src, 2.4)) > 1 else (hot_spots(src, 2.4)[0],) * 2
    lerp = lambda p, q, t: p + (q - p) * ease(t)
    return [
        (3.2, lambda t: (0.5, 0.5, lerp(1.0, 1.12, t), 0.0)),                              # establishing
        (3.6, lambda t: (lerp(a[0] - 0.06, a[0] + 0.06, t), a[1], lerp(2.2, 2.5, t), 0.8)),  # close-up, slow pan
        (3.6, lambda t: (b[0], lerp(b[1] + 0.04, b[1] - 0.04, t), lerp(2.6, 2.3, t), 0.8)),  # close-up, tilt
        (2.4, lambda t: (0.5, 0.5, lerp(1.25, 1.0, t), 0.0)),                              # back to wide
    ]


def render(out, pieces, sources, labels=None, fade=0.55, sweep_at=None):
    p = writer(out)
    font = None
    if labels:
        for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]:
            try:
                font = ImageFont.truetype(f, 26)
            except OSError:
                pass
    frames = []
    for i, (dur, fn) in enumerate(pieces):
        n = int(dur * FPS)
        for k in range(n):
            t = k / max(1, n - 1)
            cx, cy, z, dof = fn(t)
            frames.append((i, cx, cy, z, dof))
    total = len(frames)
    nf = int(fade * FPS)
    starts = {}
    for idx, fr in enumerate(frames):
        starts.setdefault(fr[0], idx)

    def frame_at(idx):
        i, cx, cy, z, dof = frames[idx % total]
        im = crop(sources[i], cx, cy, z)
        return im, dof, i

    for idx in range(total):
        im, dof, i = frame_at(idx)
        # crossfade into the next piece (and from the last back into the first, for a clean loop)
        nxt = (i + 1) % len(pieces)
        end = starts.get(nxt, total) if nxt else total
        left = end - idx
        if left <= nf:
            im2, dof2, _ = frame_at(starts.get(nxt, 0) + (nf - left))
            a = ease(1 - left / nf)
            im = Image.blend(im, im2, a)
            dof = dof + (dof2 - dof) * a
        sw = None
        if sweep_at is not None:
            s = (idx / FPS - sweep_at) / 1.4
            if -0.2 < s < 1.2:
                sw = s
        fr = finish(im, dof, sw)
        if labels and font:
            d = ImageDraw.Draw(fr)
            lab = labels[i]
            tw = d.textlength(lab, font=font)
            d.rectangle((30, H - 74, 30 + tw + 28, H - 30), fill=(0, 0, 0))
            d.rectangle((30, H - 74, 30 + tw + 28, H - 30), outline=(0, 246, 255), width=2)
            d.text((44, H - 69), lab, font=font, fill=(0, 246, 255))
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "vst":
        src = Image.open(sys.argv[2]).convert("RGB")
        pieces = shots_vst(src)
        render(sys.argv[3], pieces, [src] * len(pieces), sweep_at=0.6)
    elif mode == "pages":
        files, out = sys.argv[2:-1], sys.argv[-1]
        srcs, labels, pieces = [], [], []
        for k, f in enumerate(files):
            im = Image.open(f).convert("RGB")
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)   # room for a gentle push
            srcs.append(im)
            name = f.rsplit("/", 1)[-1].rsplit(".", 1)[0].split("_", 1)[-1].replace("-", " / " if False else " ")
            labels.append(name)
            dirn = 1 if k % 2 == 0 else -1
            pieces.append((2.6, (lambda d: (lambda t: (0.5 + d * 0.05 * (ease(t) - 0.5), 0.5, 1.0 + 0.07 * ease(t), 0.0)))(dirn)))
        render(out, pieces, srcs, labels=labels, fade=0.45)
    print("wrote", sys.argv[-1])
