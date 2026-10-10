"""Render a 30s anime-style animation ("Dawn Wish") frame by frame and pipe it to ffmpeg."""
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, DUR = 1280, 720, 24, 30
SS = 2  # supersampling for the character/overlay layer
rng = np.random.default_rng(11)
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def seg(t, a, b):
    return smooth((t - a) / (b - a))


def mixc(c1, c2, t):
    return tuple(lerp(np.array(c1, float), np.array(c2, float), t))


# ---------- static assets ----------
STARS = [(rng.uniform(0, W), rng.uniform(0, H * 0.62), rng.uniform(0.6, 2.2), rng.uniform(0, 6.28))
         for _ in range(220)]

# city skyline buildings (x, w, h, windows)
BUILD = []
x = -20
while x < W + 40:
    bw = rng.integers(36, 90)
    bh = rng.integers(60, 190)
    wins = [(i, j) for i in range(1, bw // 14) for j in range(1, bh // 18) if rng.random() < 0.45]
    BUILD.append((x, bw, bh, wins))
    x += bw + rng.integers(0, 6)

PETALS = [dict(x=rng.uniform(-100, W + 100), y=rng.uniform(-H, H), s=rng.uniform(5, 13),
               vx=rng.uniform(70, 170), vy=rng.uniform(25, 70), ph=rng.uniform(0, 6.28),
               rot=rng.uniform(-3, 3)) for _ in range(70)]

SHOOTING = [(3.0, 0.9, (130, 40), (520, 210)), (5.2, 0.8, (600, 20), (1000, 190)),
            (7.0, 1.0, (330, 60), (790, 270))]

# palettes: night -> dawn -> sunrise
SKY = {
    "night": ((8, 10, 38), (30, 22, 80), (64, 48, 120)),
    "dawn": ((40, 36, 110), (190, 90, 150), (255, 160, 130)),
    "sun": ((90, 120, 215), (250, 150, 160), (255, 214, 140)),
}


def sky_colors(t):
    k1 = seg(t, 6.5, 17)
    k2 = seg(t, 17, 27)
    out = []
    for i in range(3):
        c = mixc(SKY["night"][i], SKY["dawn"][i], k1)
        c = mixc(c, SKY["sun"][i], k2)
        out.append(c)
    return out


YY = np.linspace(0, 1, H)[:, None]


def sky_image(t):
    top, mid, bot = [np.array(c) for c in sky_colors(t)]
    a = np.clip(YY / 0.55, 0, 1)
    b = np.clip((YY - 0.55) / 0.45, 0, 1)
    col = np.where(YY < 0.55, top * (1 - a[..., None][:, 0]) + mid * a[..., None][:, 0],
                   mid * (1 - b[..., None][:, 0]) + bot * b[..., None][:, 0])
    img = np.repeat(col[:, None, :], W, axis=1)
    return img


def draw_glow(arr, cx, cy, r, color, strength):
    y0, y1 = int(max(cy - r, 0)), int(min(cy + r, H))
    x0, x1 = int(max(cx - r, 0)), int(min(cx + r, W))
    if y1 <= y0 or x1 <= x0:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r
    g = np.clip(1 - d, 0, 1) ** 2.2 * strength
    arr[y0:y1, x0:x1] += g[..., None] * np.array(color)[None, None, :]


def bezier_strand(p0, p1, p2, p3, w0, w1, n=22):
    pts_l, pts_r = [], []
    for i in range(n + 1):
        s = i / n
        x = (1 - s) ** 3 * p0[0] + 3 * (1 - s) ** 2 * s * p1[0] + 3 * (1 - s) * s ** 2 * p2[0] + s ** 3 * p3[0]
        y = (1 - s) ** 3 * p0[1] + 3 * (1 - s) ** 2 * s * p1[1] + 3 * (1 - s) * s ** 2 * p2[1] + s ** 3 * p3[1]
        dx = 3 * (1 - s) ** 2 * (p1[0] - p0[0]) + 6 * (1 - s) * s * (p2[0] - p1[0]) + 3 * s ** 2 * (p3[0] - p2[0])
        dy = 3 * (1 - s) ** 2 * (p1[1] - p0[1]) + 6 * (1 - s) * s * (p2[1] - p1[1]) + 3 * s ** 2 * (p3[1] - p2[1])
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        w = lerp(w0, w1, s) / 2
        pts_l.append((x + nx * w, y + ny * w))
        pts_r.append((x - nx * w, y - ny * w))
    return pts_l + pts_r[::-1]


def draw_character(d, t, gx, gy, light):
    """Girl seen from behind, hair and scarf blowing in the wind. Coordinates in base px (scaled by SS)."""
    S = SS
    def P(x, y): return ((gx + x) * S, (gy + y) * S)
    wind = 0.75 + 0.25 * math.sin(t * 1.7)
    sway = lambda ph, amp: math.sin(t * 3.1 + ph) * amp * wind

    hair_dark = (34, 30, 78)
    hair_mid = (62, 54, 128)
    hair_hi = (150, 130, 220)
    uniform = (28, 34, 74)
    uniform_hi = (70, 90, 160)
    skin = (246, 214, 200)
    rim = tuple(int(c) for c in light)

    # legs
    for lx in (-9, 5):
        d.polygon([P(lx, 0), P(lx + 8, 0), P(lx + 7, 70), P(lx + 1, 70)], fill=skin)
        d.polygon([P(lx - 1, 62), P(lx + 9, 62), P(lx + 11, 76), P(lx - 2, 76)], fill=(30, 28, 50))
    # skirt (pleated, swaying)
    sk = [P(-20, -42), P(20, -42)]
    for i in range(7):
        xx = 24 - i * 8
        sk.append(P(xx + sway(i, 3), 6 + (i % 2) * 3))
    d.polygon(sk, fill=(36, 38, 92))
    for i in range(1, 7):
        xx = 24 - i * 8
        d.line([P(lerp(-20, 20, i / 7), -40), P(xx + sway(i, 3), 5)], fill=(54, 58, 128), width=2 * S)
    # torso (sailor top)
    d.polygon([P(-19, -42), P(19, -42), P(16, -104), P(-16, -104)], fill=uniform)
    d.polygon([P(-16, -104), P(16, -104), P(12, -94), P(-12, -94)], fill=uniform_hi)
    # sailor collar
    d.polygon([P(-17, -106), P(17, -106), P(18, -78), P(0, -70), P(-18, -78)], fill=(236, 240, 252))
    d.polygon([P(-17, -106), P(17, -106), P(18, -96), P(-18, -96)], fill=(48, 62, 130))
    # arms (slightly raised toward the sky on the right)
    d.polygon([P(-17, -100), P(-25, -98), P(-31, -60), P(-23, -58)], fill=uniform)
    d.polygon([P(-31, -60), P(-23, -58), P(-22, -48), P(-30, -49)], fill=skin)
    # neck
    d.rectangle([P(-5, -116)[0], P(-5, -116)[1], P(5, -104)[0], P(5, -104)[1]], fill=skin)

    # scarf tails (red) flowing right
    for k, (off, ln, wv) in enumerate(((0, 130, 0.0), (8, 100, 1.2))):
        base = (10, -100 + off)
        p0 = P(*base)
        p1 = P(base[0] + ln * .35, base[1] + 6 + sway(wv, 14))
        p2 = P(base[0] + ln * .7, base[1] - 4 + sway(wv + 1, 22))
        p3 = P(base[0] + ln, base[1] + 8 + sway(wv + 2, 26))
        d.polygon(bezier_strand(p0, p1, p2, p3, 14 * S, 6 * S), fill=(220, 54, 80) if k == 0 else (170, 36, 66))
    d.ellipse([P(-18, -112)[0], P(-18, -112)[1], P(18, -96)[0], P(18, -96)[1]], fill=(226, 60, 86))

    # hair back (head mass)
    d.ellipse([P(-24, -176)[0], P(-24, -176)[1], P(24, -118)[0], P(24, -118)[1]], fill=hair_dark)
    # long flowing strands (back layer)
    anchors = [(-14, -140), (-6, -150), (2, -156), (10, -150), (16, -140), (18, -128), (12, -122), (-8, -124)]
    lens = [120, 150, 175, 165, 150, 125, 105, 90]
    for i, ((ax, ay), ln) in enumerate(zip(anchors, lens)):
        ph = i * 0.7
        p0 = P(ax, ay)
        p1 = P(ax + ln * .30, ay + 12 + sway(ph, 8))
        p2 = P(ax + ln * .62, ay + 34 + sway(ph + 1, 20))
        p3 = P(ax + ln, ay + 28 + i * 3 + sway(ph + 2, 30))
        col = hair_dark if i % 3 == 0 else (hair_mid if i % 3 == 1 else (48, 42, 104))
        d.polygon(bezier_strand(p0, p1, p2, p3, 22 * S, 2 * S), fill=col)
    # highlight strands
    for i, ((ax, ay), ln) in enumerate(zip(anchors[1:6], lens[1:6])):
        ph = i * 0.7 + 0.35
        p0 = P(ax + 1, ay + 2)
        p1 = P(ax + ln * .30, ay + 10 + sway(ph, 8))
        p2 = P(ax + ln * .62, ay + 30 + sway(ph + 1, 20))
        p3 = P(ax + ln * .95, ay + 26 + i * 3 + sway(ph + 2, 30))
        d.polygon(bezier_strand(p0, p1, p2, p3, 5 * S, 1 * S), fill=hair_hi)
    # head crown & bangs edge highlight
    d.pieslice([P(-22, -174)[0], P(-22, -174)[1], P(22, -122)[0], P(22, -122)[1]], 200, 340, fill=hair_mid)
    d.arc([P(-24, -176)[0], P(-24, -176)[1], P(24, -118)[0], P(24, -118)[1]], 205, 335,
          fill=(255, 220, 190), width=2 * S)
    # ears peek
    d.ellipse([P(-26, -140)[0], P(-26, -140)[1], P(-19, -130)[0], P(-19, -130)[1]], fill=skin)
    # ribbon
    rx, ry = 0, -171
    d.polygon([P(rx, ry), P(rx - 18 + sway(0, 3), ry - 12), P(rx - 16 + sway(0, 3), ry + 8)], fill=(255, 120, 150))
    d.polygon([P(rx, ry), P(rx + 18 + sway(1, 5), ry - 14), P(rx + 17 + sway(1, 5), ry + 9)], fill=(255, 120, 150))
    d.ellipse([P(rx - 4, ry - 4)[0], P(rx - 4, ry - 4)[1], P(rx + 4, ry + 4)[0], P(rx + 4, ry + 4)[1]], fill=(255, 220, 230))
    # ribbon tails
    for k in (0, 1):
        p0 = P(rx, ry + 2)
        p1 = P(rx + 20, ry + 14 + sway(k, 6))
        p2 = P(rx + 40, ry + 18 + sway(k + 1, 10))
        p3 = P(rx + 60 + k * 12, ry + 14 + sway(k + 2, 14))
        d.polygon(bezier_strand(p0, p1, p2, p3, 7 * S, 2 * S), fill=(255, 120, 150))
    # rim light along back-left of hair/body facing the rising sun (right side)
    d.line([P(22, -150), P(24, -128)], fill=rim + (255,), width=2 * S) if False else None


def petal_shape(d, x, y, s, rot, col):
    pts = []
    for a in np.linspace(0, 2 * math.pi, 10, endpoint=False):
        r = s * (1.0 if (int(a * 10) % 2 == 0) else 0.7)
        px, py = math.cos(a) * r * 1.0, math.sin(a) * r * 0.55
        c, sn = math.cos(rot), math.sin(rot)
        pts.append(((x + px * c - py * sn) * SS, (y + px * sn + py * c) * SS))
    d.polygon(pts, fill=col)


title_font_big = ImageFont.truetype(FONT, 78)
title_font_sm = ImageFont.truetype(FONT, 30)
sub_font = ImageFont.truetype(FONT, 34)


def text_center(img, txt, y, font, alpha, fill=(255, 255, 255), glow=(180, 160, 255)):
    if alpha <= 0.01:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bb = d.textbbox((0, 0), txt, font=font)
    x = (W - (bb[2] - bb[0])) / 2
    d.text((x, y), txt, font=font, fill=glow + (255,))
    g = layer.filter(ImageFilter.GaussianBlur(10))
    d2 = ImageDraw.Draw(g)
    layer2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer2).text((x, y), txt, font=font, fill=fill + (255,))
    g = Image.alpha_composite(g, layer2)
    a = g.split()[3].point(lambda v: int(v * alpha))
    g.putalpha(a)
    img.alpha_composite(g)


def render(f):
    t = f / FPS
    arr = sky_image(t)

    # camera push-in factor (slow)
    zoom = 1.0 + 0.06 * t / DUR

    # stars
    star_vis = 1 - seg(t, 8, 17)
    if star_vis > 0:
        for sx, sy, sr, ph in STARS:
            tw = 0.55 + 0.45 * math.sin(t * 2.4 + ph)
            v = star_vis * tw
            xi, yi = int(sx), int(sy)
            r = int(math.ceil(sr))
            arr[max(yi - r, 0):yi + r, max(xi - r, 0):xi + r] += 255 * v * 0.9

    # moon (sinks and fades toward dawn)
    moon_a = 1 - seg(t, 7, 18)
    if moon_a > 0:
        mx, my = 250, lerp(120, 330, seg(t, 0, 18))
        draw_glow(arr, mx, my, 160, (170, 190, 255), 0.55 * moon_a)

    # sun glow rising
    sun_k = seg(t, 15, 29)
    sun_y = lerp(H * 0.80, H * 0.50, sun_k)
    sun_x = W * 0.62
    sun_a = seg(t, 13, 20)
    if sun_a > 0:
        draw_glow(arr, sun_x, sun_y, 700, (255, 170, 120), 0.65 * sun_a)
        draw_glow(arr, sun_x, sun_y, 260, (255, 230, 170), 0.9 * sun_a)
        draw_glow(arr, sun_x, sun_y, 90, (255, 255, 235), 1.0 * sun_a)

    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # moon disc
    if moon_a > 0:
        mx, my = 250, lerp(120, 330, seg(t, 0, 18))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse([mx - 48, my - 48, mx + 48, my + 48], fill=(244, 244, 255, int(255 * moon_a)))
        ld.ellipse([mx - 20, my - 30, mx - 2, my - 12], fill=(214, 216, 240, int(255 * moon_a)))
        ld.ellipse([mx + 12, my + 6, mx + 32, my + 26], fill=(220, 222, 244, int(255 * moon_a)))
        img.alpha_composite(layer)

    # sun disc
    if sun_a > 0:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse([sun_x - 58, sun_y - 58, sun_x + 58, sun_y + 58], fill=(255, 250, 230, int(255 * sun_a)))
        img.alpha_composite(layer)

    # shooting stars
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for t0, dur, p0, p1 in SHOOTING:
        u = (t - t0) / dur
        if 0 <= u <= 1:
            head = (lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u))
            tail_u = max(u - 0.35, 0)
            tail = (lerp(p0[0], p1[0], tail_u), lerp(p0[1], p1[1], tail_u))
            a = math.sin(u * math.pi)
            for k in range(14):
                s = k / 14
                x = lerp(tail[0], head[0], s)
                y = lerp(tail[1], head[1], s)
                r = 1 + 3.2 * s
                ld.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, int(220 * s * a)))
            r = 7
            ld.ellipse([head[0] - r, head[1] - r, head[0] + r, head[1] + r], fill=(255, 245, 210, int(255 * a)))
    layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    img.alpha_composite(layer)

    # city skyline silhouette (far), parallax drift
    skyline_col = mixc((12, 14, 44), (52, 36, 92), seg(t, 6, 20))
    skyline_col = mixc(skyline_col, (96, 66, 120), seg(t, 20, 29))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    drift = -t * 2.5
    base_y = H - 150
    for bx, bw, bh, wins in BUILD:
        x0 = bx + drift
        ld.rectangle([x0, base_y - bh, x0 + bw, base_y + 40], fill=tuple(int(c) for c in skyline_col) + (255,))
        win_on = 1 - seg(t, 12, 22) * 0.75
        for i, j in wins:
            if (int(t * 0.7) + i * 7 + j * 3) % 11 == 0:
                continue
            ld.rectangle([x0 + i * 14, base_y - bh + j * 18, x0 + i * 14 + 6, base_y - bh + j * 18 + 8],
                         fill=(255, 220, 140, int(230 * win_on)))
    img.alpha_composite(layer)

    # sun-side haze over city
    haze = Image.new("RGBA", (W, H), (255, 150, 120, int(70 * seg(t, 14, 26))))
    mask = Image.linear_gradient("L").resize((W, 400))
    hm = Image.new("L", (W, H), 0)
    hm.paste(mask, (0, H - 400))
    haze.putalpha(hm.point(lambda v: int(v * 0.5 * seg(t, 14, 26))))
    img.alpha_composite(haze)

    # hill (foreground)
    hill_col = mixc((6, 8, 26), (28, 22, 54), seg(t, 6, 22))
    hill_col = mixc(hill_col, (60, 40, 70), seg(t, 22, 29))
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    pts = [(0, H * SS)]
    for xx in range(0, W + 20, 20):
        yy = H - 130 + 28 * math.sin(xx / 210.0 + 0.6) - 16 * math.sin(xx / 70.0) - (xx / W) * 20
        pts.append((xx * SS, yy * SS))
    pts.append((W * SS, H * SS))
    ld.polygon(pts, fill=tuple(int(c) for c in hill_col) + (255,))
    # grass blades
    grass_col = tuple(int(c * 1.3) for c in hill_col) + (255,)
    for gi in range(0, W, 9):
        gy0 = H - 130 + 28 * math.sin(gi / 210.0 + 0.6) - 16 * math.sin(gi / 70.0) - (gi / W) * 20
        sw = math.sin(t * 2.5 + gi * 0.07) * 6
        hh = 14 + (gi * 7 % 13)
        ld.polygon([((gi - 2) * SS, gy0 * SS), ((gi + 2) * SS, gy0 * SS),
                    ((gi + sw + 6) * SS, (gy0 - hh) * SS)], fill=grass_col)

    # character on the hill
    gx = 470
    gy = H - 130 + 28 * math.sin(gx / 210.0 + 0.6) - 16 * math.sin(gx / 70.0) - (gx / W) * 20 + 4
    # feet are the origin -> body drawn upward; legs drawn from y=0 downward in local coords, so shift up
    light = (255, 190, 140)
    draw_character(ld, t, gx, gy - 76 - 4, light)
    # slight rim glow from the sun on the right side of the character
    layer = layer.resize((W, H), Image.LANCZOS)
    img.alpha_composite(layer)

    # petals (drawn on SS layer for smooth edges)
    pl = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pl)
    pa = seg(t, 7, 11)
    for p in PETALS:
        px = (p["x"] + p["vx"] * t) % (W + 200) - 100
        py = (p["y"] + p["vy"] * t + 18 * math.sin(t * 2 + p["ph"])) % (H + 200) - 100
        if pa <= 0:
            break
        col = (255, 190, 210, int(235 * pa))
        petal_shape(pd, px, py, p["s"], p["rot"] * t + p["ph"], col)
    pl = pl.resize((W, H), Image.LANCZOS)
    img.alpha_composite(pl)

    # sparkle bloom at sunrise
    k = seg(t, 19.2, 20.2) * (1 - seg(t, 20.2, 22.5))
    if k > 0:
        fl = Image.new("RGBA", (W, H), (255, 240, 210, int(110 * k)))
        img.alpha_composite(fl)

    # titles
    text_center(img, "晨 曦 之 愿", 250, title_font_big, seg(t, 0.8, 2.2) * (1 - seg(t, 8.0, 9.5)))
    text_center(img, "Dawn Wish", 345, title_font_sm, seg(t, 1.6, 3.0) * (1 - seg(t, 8.0, 9.5)),
                glow=(150, 130, 230))
    text_center(img, "当夜幕褪去，愿望便会随风而来", 140, sub_font, seg(t, 11, 12.5) * (1 - seg(t, 17, 18.5)),
                glow=(255, 150, 190))
    text_center(img, "新的一天，开始了", 200, sub_font, seg(t, 22.5, 24) * (1 - seg(t, 28.5, 29.5)),
                fill=(255, 255, 255), glow=(255, 160, 130))
    text_center(img, "— END —", 620, title_font_sm, seg(t, 26, 27.5) * (1 - seg(t, 29.2, 30)),
                glow=(255, 190, 150))

    # letterbox + vignette
    out = np.asarray(img.convert("RGB"), dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.35 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) * 0.5
    out *= v[..., None]
    # fade in / out
    fade = min(t / 1.2, 1) * min((DUR - t) / 1.2, 1)
    out *= fade
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    out = sys.argv[1]
    audio = sys.argv[2]
    only = int(sys.argv[3]) if len(sys.argv) > 3 else None
    if only is not None:
        Image.fromarray(render(only)).save(out)
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(FPS * DUR):
        p.stdin.write(render(f).tobytes())
        if f % 48 == 0:
            print("frame", f, flush=True)
    p.stdin.close()
    p.wait()


if __name__ == "__main__":
    main()
