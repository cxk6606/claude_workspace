"""Render a 3840x2160 (16:9, 4K) cover for 'Dawn Wish' reusing the character drawing from make_video.py."""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_video as mv

LW, LH = 1280, 720          # logical canvas
SS = 3                      # -> 3840x2160
W, H = LW * SS, LH * SS
mv.SS = SS
rng = np.random.default_rng(5)
FONT = mv.FONT


def glow(arr, cx, cy, r, color, strength):
    y0, y1 = int(max(cy - r, 0)), int(min(cy + r, H))
    x0, x1 = int(max(cx - r, 0)), int(min(cx + r, W))
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r
    g = np.clip(1 - d, 0, 1) ** 2.2 * strength
    arr[y0:y1, x0:x1] += g[..., None] * np.array(color, np.float32)


# ---- sky ----
top, mid, bot = np.array((70, 70, 160), np.float32), np.array((225, 110, 160), np.float32), np.array((255, 190, 140), np.float32)
yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
a = np.clip(yy / 0.6, 0, 1)
b = np.clip((yy - 0.6) / 0.4, 0, 1)
col = np.where(yy < 0.6, top * (1 - a) + mid * a, mid * (1 - b) + bot * b)
arr = np.repeat(col, W, axis=1).astype(np.float32)

# faint stars at the top
for _ in range(160):
    x, y = rng.uniform(0, W), rng.uniform(0, H * 0.4)
    r = int(rng.uniform(2, 6))
    fade = 1 - y / (H * 0.4)
    arr[int(y):int(y) + r, int(x):int(x) + r] += 255 * rng.uniform(0.3, 1) * fade * 0.7

sun_x, sun_y = 3050, 1290
glow(arr, sun_x, sun_y, 2300, (255, 170, 120), 0.7)
glow(arr, sun_x, sun_y, 850, (255, 230, 170), 0.9)
glow(arr, sun_x, sun_y, 290, (255, 255, 240), 1.0)
img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

# sun disc, soft
lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(lay).ellipse([sun_x - 190, sun_y - 190, sun_x + 190, sun_y + 190], fill=(255, 250, 232, 255))
img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(3)))

# long light streaks (god rays)
rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
rd = ImageDraw.Draw(rays)
for i in range(18):
    ang = math.radians(rng.uniform(-170, -10))
    wd = math.radians(rng.uniform(1.0, 3.0))
    L = 3500
    rd.polygon([(sun_x, sun_y), (sun_x + math.cos(ang - wd) * L, sun_y + math.sin(ang - wd) * L),
                (sun_x + math.cos(ang + wd) * L, sun_y + math.sin(ang + wd) * L)],
               fill=(255, 220, 190, int(rng.uniform(10, 26))))
img.alpha_composite(rays.filter(ImageFilter.GaussianBlur(14)))

# ---- skyline ----
lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ld = ImageDraw.Draw(lay)
base_y = H - 400
x = -60
sk = (92, 64, 124, 255)
while x < W + 60:
    bw = int(rng.integers(110, 270))
    bh = int(rng.integers(200, 620))
    if 2500 < x < 3650:
        bh = int(rng.integers(120, 250))
    ld.rectangle([x, base_y - bh, x + bw, base_y + 200], fill=sk)
    for i in range(1, bw // 42):
        for j in range(1, bh // 54):
            if rng.random() < 0.4:
                ld.rectangle([x + i * 42, base_y - bh + j * 54, x + i * 42 + 18, base_y - bh + j * 54 + 24],
                             fill=(255, 224, 160, 215))
    x += bw + int(rng.integers(0, 16))
img.alpha_composite(lay)
haze = Image.new("RGBA", (W, H), (255, 160, 130, 0))
m = Image.linear_gradient("L").resize((W, 1100))
hm = Image.new("L", (W, H), 0)
hm.paste(m, (0, H - 1500))
haze.putalpha(hm.point(lambda v: int(v * 0.42)))
img.alpha_composite(haze)

# ---- hill + grass + character ----
def hill_y(xl):  # logical x -> logical y
    return LH - 120 + 30 * math.sin(xl / 210.0 + 0.2) - 14 * math.sin(xl / 70.0) - (xl / LW) * 10

lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ld = ImageDraw.Draw(lay)
hcol = (52, 36, 70, 255)
pts = [(0, H)] + [(xl * SS, hill_y(xl) * SS) for xl in range(0, LW + 10, 10)] + [(W, H)]
ld.polygon(pts, fill=hcol)
for gi in range(0, LW, 4):
    gy0 = hill_y(gi)
    sw = math.sin(gi * 0.09) * 5
    hh = 10 + (gi * 7 % 17)
    ld.polygon([((gi - 1.6) * SS, gy0 * SS), ((gi + 1.6) * SS, gy0 * SS), ((gi + sw + 4) * SS, (gy0 - hh) * SS)],
               fill=(68, 48, 88, 255))
K = 1.9
gx = 330
feet = hill_y(gx) + 8
mv.draw_character(ld, 1.05, gx, feet - 80 * K, (255, 190, 140), K=K)
img.alpha_composite(lay)

# ---- petals ----
pl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
pd = ImageDraw.Draw(pl)
for _ in range(95):
    px, py = rng.uniform(0, LW), rng.uniform(0, LH * 0.95)
    s = rng.uniform(5, 16) * (1.6 if rng.random() < 0.12 else 1)
    mv.petal_shape(pd, px, py, s, rng.uniform(0, 6.28), (255, 192, 214, int(rng.uniform(170, 245))))
img.alpha_composite(pl)

# ---- title ----
def text(im, txt, cx, y, size, fill, glow_c, blur):
    f = ImageFont.truetype(FONT, size)
    d0 = ImageDraw.Draw(im)
    bb = d0.textbbox((0, 0), txt, font=f)
    x = cx - (bb[2] - bb[0]) / 2
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((x, y), txt, font=f, fill=glow_c + (255,))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(blur)))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((x + 6, y + 8), txt, font=f, fill=(60, 20, 70, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    t_ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(t_).text((x, y), txt, font=f, fill=fill + (255,))
    im.alpha_composite(t_)

tx = 2520
text(img, "晨 曦 之 愿", tx, 250, 400, (255, 255, 255), (255, 140, 190), 36)
text(img, "D A W N   W I S H", tx, 720, 112, (255, 240, 225), (255, 160, 130), 18)
text(img, "愿望已实现。代价：你。", tx, 890, 100, (255, 255, 255), (150, 90, 200), 16)
text(img, "第 一 集 · 坠 落 的 星 屑", tx, 1030, 86, (255, 226, 214), (255, 140, 120), 14)

# vignette + grain
out = np.asarray(img.convert("RGB"), dtype=np.float32)
yy2, xx2 = np.mgrid[0:H:4, 0:W:4]
v = 1 - 0.32 * (((xx2 - W / 2) / (W / 2)) ** 2 + ((yy2 - H / 2) / (H / 2)) ** 2) * 0.5
v = np.array(Image.fromarray((v * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR), np.float32) / 255
out = out * v[..., None] + rng.normal(0, 2.2, out.shape[:2])[..., None]
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(sys.argv[1], optimize=True)
print("saved", sys.argv[1], W, H)
